# -*- coding: UTF-8 -*-
#
# Copyright (C) 2020, Team Kodi
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# pylint: disable=missing-docstring

"""TMDb TV episode details: fetch, map, cache, and persist."""

from __future__ import absolute_import, unicode_literals

import os
import sqlite3
import time
from datetime import datetime, timedelta

try:
    from datetime import timezone
except ImportError:
    timezone = None


def _utc_now():
    if timezone is not None:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.utcnow()

from . import tmdbapi

DEFAULT_IMAGE_BASE = 'https://image.tmdb.org/t/p/w500'
CACHE_MAX_AGE_DAYS = 30
RATE_LIMIT_MAX = 40
RATE_LIMIT_WINDOW_SECONDS = 10.0


def map_episode_response(api_data, image_base=DEFAULT_IMAGE_BASE):
    """
    Map a TMDb TV episode API payload to the local episodes table shape.

    :param api_data: JSON object from GET /tv/{series_id}/season/{s}/episode/{e}
    :param image_base: base URL for still_path images
    :return: dict ready for EpisodeStore.upsert
    """
    still_path = api_data.get('still_path')
    poster_url = '{}{}'.format(image_base, still_path) if still_path else None
    return {
        'id': api_data.get('id'),
        'series_id': api_data.get('series_id'),
        'season_number': api_data.get('season_number'),
        'episode_number': api_data.get('episode_number'),
        'name': api_data.get('name') or '',
        'air_date': api_data.get('air_date') or None,
        'overview': api_data.get('overview') or '',
        'rating': api_data.get('vote_average'),
        'poster_url': poster_url,
        'last_synced': _utc_now().isoformat(timespec='seconds') + 'Z',
    }


def _error_status(result):
    if not isinstance(result, dict) or 'error' not in result:
        return None
    message = result.get('error', '')
    if 'Error code: 404' in message:
        return 404
    if 'Error code: 401' in message:
        return 401
    if 'Error code: 429' in message:
        return 429
    if 'Error code: 500' in message:
        return 500
    return None


def fetch_episode(series_id, season_number, episode_number, language=None, append_to_response=None):
    """
    Fetch one TV episode from TMDb.

    :return: mapped episode dict, or None if not found (404)
    :raises: RuntimeError on auth/server errors after retries
    """
    raw = tmdbapi.get_tv_episode(
        series_id,
        season_number,
        episode_number,
        language=language,
        append_to_response=append_to_response,
    )
    status = _error_status(raw)
    if status == 404:
        return None
    if status in (401, 429, 500) or (isinstance(raw, dict) and 'error' in raw):
        raise RuntimeError(raw.get('error', 'TMDb episode request failed'))
    payload = dict(raw)
    payload.setdefault('series_id', int(series_id))
    payload.setdefault('season_number', int(season_number))
    payload.setdefault('episode_number', int(episode_number))
    return map_episode_response(payload)


class EpisodeStore(object):
    """SQLite-backed episode cache."""

    _SCHEMA = '''
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY,
            series_id INTEGER NOT NULL,
            season_number INTEGER NOT NULL,
            episode_number INTEGER NOT NULL,
            name TEXT,
            air_date TEXT,
            overview TEXT,
            rating REAL,
            poster_url TEXT,
            last_synced TEXT NOT NULL,
            UNIQUE(series_id, season_number, episode_number)
        )
    '''

    def __init__(self, db_path):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(self._SCHEMA)
        self._conn.commit()

    def close(self):
        self._conn.close()

    def get(self, series_id, season_number, episode_number):
        row = self._conn.execute(
            '''
            SELECT * FROM episodes
            WHERE series_id = ? AND season_number = ? AND episode_number = ?
            ''',
            (int(series_id), int(season_number), int(episode_number)),
        ).fetchone()
        return dict(row) if row else None

    def is_fresh(self, series_id, season_number, episode_number, max_age_days=CACHE_MAX_AGE_DAYS):
        row = self.get(series_id, season_number, episode_number)
        if not row or not row.get('last_synced'):
            return False
        try:
            synced = datetime.strptime(row['last_synced'], '%Y-%m-%dT%H:%M:%SZ')
        except ValueError:
            return False
        return synced >= _utc_now() - timedelta(days=max_age_days)

    def upsert(self, episode):
        self._conn.execute(
            '''
            INSERT INTO episodes (
                id, series_id, season_number, episode_number,
                name, air_date, overview, rating, poster_url, last_synced
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(series_id, season_number, episode_number) DO UPDATE SET
                id = excluded.id,
                name = excluded.name,
                air_date = excluded.air_date,
                overview = excluded.overview,
                rating = excluded.rating,
                poster_url = excluded.poster_url,
                last_synced = excluded.last_synced
            ''',
            (
                episode['id'],
                episode['series_id'],
                episode['season_number'],
                episode['episode_number'],
                episode.get('name'),
                episode.get('air_date'),
                episode.get('overview'),
                episode.get('rating'),
                episode.get('poster_url'),
                episode['last_synced'],
            ),
        )
        self._conn.commit()


class _RateLimiter(object):
    def __init__(self, max_calls=RATE_LIMIT_MAX, window_seconds=RATE_LIMIT_WINDOW_SECONDS):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._timestamps = []

    def wait(self):
        now = time.time()
        self._timestamps = [t for t in self._timestamps if now - t < self.window_seconds]
        if len(self._timestamps) >= self.max_calls:
            sleep_for = self.window_seconds - (now - self._timestamps[0]) + 0.05
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.time()
            self._timestamps = [t for t in self._timestamps if now - t < self.window_seconds]
        self._timestamps.append(time.time())


def sync_episodes(episode_keys, store, language=None, skip_fresh=True, logger=None):
    """
    Fetch and upsert multiple episodes.

    :param episode_keys: iterable of (series_id, season_number, episode_number)
    :param store: EpisodeStore instance
    :param skip_fresh: skip API call when cache entry is younger than CACHE_MAX_AGE_DAYS
    :param logger: optional callable(message) for errors and progress
    :return: dict with synced, skipped, not_found, errors counts and error messages
    """
    limiter = _RateLimiter()
    summary = {'synced': 0, 'skipped': 0, 'not_found': 0, 'errors': 0, 'messages': []}

    def log(msg):
        if logger:
            logger(msg)

    for series_id, season_number, episode_number in episode_keys:
        if skip_fresh and store.is_fresh(series_id, season_number, episode_number):
            summary['skipped'] += 1
            continue
        limiter.wait()
        try:
            episode = fetch_episode(series_id, season_number, episode_number, language=language)
        except RuntimeError as exc:
            summary['errors'] += 1
            message = 'series={} s{}e{}: {}'.format(series_id, season_number, episode_number, exc)
            summary['messages'].append(message)
            log(message)
            continue
        if episode is None:
            summary['not_found'] += 1
            log('Episode not found: series={} season={} episode={}'.format(
                series_id, season_number, episode_number))
            continue
        store.upsert(episode)
        summary['synced'] += 1
        log('Synced series={} s{}e{} ({})'.format(
            series_id, season_number, episode_number, episode.get('name')))

    return summary


def default_store_path():
    base = os.environ.get('TMDB_EPISODE_DB_PATH')
    if base:
        return base
    return os.path.join(os.path.expanduser('~'), '.tmdb_episodes.sqlite3')
