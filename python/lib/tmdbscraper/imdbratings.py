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
#
# IMDb ratings based on code in metadata.themoviedb.org.python by Team Kodi
# pylint: disable=missing-docstring

import json
import re
from . import api_utils
from . import get_imdb_id

IMDB_RATINGS_URL = 'https://www.imdb.com/title/{}/'
IMDB_GRAPHQL_URL = 'https://caching.graphql.imdb.com/'
IMDB_GRAPHQL_QUERY = (
    'query TitleRatings($id: ID!) { title(id: $id) { '
    'ratingsSummary { aggregateRating voteCount topRanking { rank } } } }'
)
IMDB_LDJSON_REGEX = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)
IMDB_TOP250_REGEX = re.compile(r'Top rated movie #(\d+)')

# previous IMDB page design before June 2021
IMDB_RATING_REGEX_PREVIOUS = re.compile(r'itemprop="ratingValue".*?>.*?([\d.]+).*?<')
IMDB_VOTES_REGEX_PREVIOUS = re.compile(r'itemprop="ratingCount".*?>.*?([\d,]+).*?<')
IMDB_TOP250_REGEX_PREVIOUS = re.compile(r'Top Rated Movies #(\d+)')

HEADERS = (
    ('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'),
    ('Accept', 'application/json'),
)
GRAPHQL_HEADERS = (
    ('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'),
    ('Accept', 'application/graphql+json, application/json'),
    ('Content-Type', 'application/json'),
    ('Origin', 'https://www.imdb.com'),
    ('Referer', 'https://www.imdb.com/'),
    ('x-imdb-client-name', 'imdb-web-next'),
)

def get_details(uniqueids):
    imdb_id = get_imdb_id(uniqueids)
    if not imdb_id:
        return {}
    votes, rating, top250 = _get_ratinginfo(imdb_id)
    return _assemble_imdb_result(votes, rating, top250)

def _get_ratinginfo(imdb_id):
    votes, rating, top250 = _get_ratinginfo_graphql(imdb_id)
    if votes is not None or rating is not None or top250 is not None:
        return votes, rating, top250
    return _get_ratinginfo_html(imdb_id)

def _get_ratinginfo_graphql(imdb_id):
    api_utils.set_headers(dict(GRAPHQL_HEADERS))
    response = api_utils.load_info(
        IMDB_GRAPHQL_URL,
        data={'query': IMDB_GRAPHQL_QUERY, 'variables': {'id': imdb_id}},
        default={},
    )
    return _parse_imdb_graphql(response)

def _get_ratinginfo_html(imdb_id):
    api_utils.set_headers(dict(HEADERS))
    response = api_utils.load_info(IMDB_RATINGS_URL.format(imdb_id), default = '', resp_type='text')
    return _parse_imdb_result(response)

def _parse_imdb_graphql(response):
    try:
        ratings = ((response or {}).get('data') or {}).get('title') or {}
        ratings = ratings.get('ratingsSummary') or {}
    except AttributeError:
        return None, None, None

    rating = ratings.get('aggregateRating')
    votes = ratings.get('voteCount')
    top_ranking = ratings.get('topRanking') or {}
    try:
        top250 = top_ranking.get('rank')
    except AttributeError:
        top250 = None

    try:
        rating = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating = None
    try:
        votes = int(votes) if votes is not None else None
    except (TypeError, ValueError):
        votes = None
    try:
        top250 = int(top250) if top250 is not None else None
    except (TypeError, ValueError):
        top250 = None

    return votes, rating, top250

def _assemble_imdb_result(votes, rating, top250):
    result = {}
    if top250:
        result['info'] = {'top250': top250}
    if votes and rating:
        result['ratings'] = {'imdb': {'votes': votes, 'rating': rating}}
    return result

def _parse_imdb_result(input_html):
    rating, votes = _parse_imdb_rating_and_votes(input_html)
    if rating is None or votes is None:
        # try previous parsers
        rating = _parse_imdb_rating_previous(input_html)
        votes = _parse_imdb_votes_previous(input_html)
    top250 = _parse_imdb_top250(input_html)
    if top250 is None:
        top250 = _parse_imdb_top250_previous(input_html)

    return votes, rating, top250

def _parse_imdb_rating_and_votes(input_html):
    match = re.search(IMDB_LDJSON_REGEX, input_html)
    if not match:
        return None, None

    try:
        ldjson = json.loads(match.group(1).replace('\n', ''))
    except json.decoder.JSONDecodeError:
        return None, None

    try:
        aggregateRating = ldjson.get('aggregateRating', {})
        rating_value = aggregateRating.get('ratingValue')
        return rating_value, aggregateRating.get('ratingCount')
    except AttributeError:
        return None, None

def _parse_imdb_top250(input_html):
    match = re.search(IMDB_TOP250_REGEX, input_html)
    if match:
        return int(match.group(1))
    return None

def _parse_imdb_rating_previous(input_html):
    match = re.search(IMDB_RATING_REGEX_PREVIOUS, input_html)
    if (match):
        return float(match.group(1))
    return None

def _parse_imdb_votes_previous(input_html):
    match = re.search(IMDB_VOTES_REGEX_PREVIOUS, input_html)
    if (match):
        return int(match.group(1).replace(',', ''))
    return None

def _parse_imdb_top250_previous(input_html):
    match = re.search(IMDB_TOP250_REGEX_PREVIOUS, input_html)
    if (match):
        return int(match.group(1))
    return None
