# pylint: disable=invalid-name,protected-access
import os
import tempfile
import unittest
from unittest import mock

from python.lib.tmdbscraper import tv_episodes
from python.lib.tmdbscraper import tmdbapi


GOT_S1E1 = {
    'air_date': '2011-04-17',
    'episode_number': 1,
    'id': 349232,
    'name': 'Winter Is Coming',
    'overview': 'Lord Stark is torn between his family and an old friend.',
    'production_code': '101',
    'season_number': 1,
    'still_path': '/still.jpg',
    'vote_average': 8.5,
    'vote_count': 3000,
}


class TestMapEpisodeResponse(unittest.TestCase):
    def test_map_episode_response__golden_path(self):
        payload = dict(GOT_S1E1)
        payload['series_id'] = 1399

        row = tv_episodes.map_episode_response(payload)

        self.assertEqual(349232, row['id'])
        self.assertEqual(1399, row['series_id'])
        self.assertEqual(1, row['season_number'])
        self.assertEqual(1, row['episode_number'])
        self.assertEqual('Winter Is Coming', row['name'])
        self.assertEqual('2011-04-17', row['air_date'])
        self.assertEqual(8.5, row['rating'])
        self.assertEqual('https://image.tmdb.org/t/p/w500/still.jpg', row['poster_url'])
        self.assertTrue(row['last_synced'].endswith('Z'))

    def test_map_episode_response__no_still(self):
        payload = dict(GOT_S1E1, still_path=None, series_id=1399)
        row = tv_episodes.map_episode_response(payload)
        self.assertIsNone(row['poster_url'])


class TestFetchEpisode(unittest.TestCase):
    @mock.patch('python.lib.tmdbscraper.tmdbapi.get_tv_episode')
    def test_fetch_episode__success(self, mock_get):
        mock_get.return_value = dict(GOT_S1E1)

        episode = tv_episodes.fetch_episode(1399, 1, 1)

        mock_get.assert_called_once_with(1399, 1, 1, language=None, append_to_response=None)
        self.assertEqual('Winter Is Coming', episode['name'])
        self.assertEqual(1399, episode['series_id'])

    @mock.patch('python.lib.tmdbscraper.tmdbapi.get_tv_episode')
    def test_fetch_episode__not_found(self, mock_get):
        mock_get.return_value = {'error': 'remote site unable to fulfill the request\nError code: 404'}

        episode = tv_episodes.fetch_episode(1399, 99, 99)

        self.assertIsNone(episode)

    @mock.patch('python.lib.tmdbscraper.tmdbapi.get_tv_episode')
    def test_fetch_episode__rate_limited_raises(self, mock_get):
        mock_get.return_value = {'error': 'remote site unable to fulfill the request\nError code: 429'}

        with self.assertRaises(RuntimeError):
            tv_episodes.fetch_episode(1399, 1, 1)


class TestEpisodeStore(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tempdir, 'episodes.sqlite3')
        self.store = tv_episodes.EpisodeStore(self.db_path)

    def tearDown(self):
        self.store.close()

    def test_upsert_and_get(self):
        row = tv_episodes.map_episode_response(dict(GOT_S1E1, series_id=1399))
        self.store.upsert(row)

        stored = self.store.get(1399, 1, 1)
        self.assertEqual('Winter Is Coming', stored['name'])
        self.assertEqual(8.5, stored['rating'])

    def test_is_fresh_after_upsert(self):
        row = tv_episodes.map_episode_response(dict(GOT_S1E1, series_id=1399))
        self.store.upsert(row)
        self.assertTrue(self.store.is_fresh(1399, 1, 1))


class TestSyncEpisodes(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tempdir, 'episodes.sqlite3')
        self.store = tv_episodes.EpisodeStore(self.db_path)

    def tearDown(self):
        self.store.close()

    @mock.patch('python.lib.tmdbscraper.tv_episodes.fetch_episode')
    def test_sync_episodes__mixed_results(self, mock_fetch):
        mock_fetch.side_effect = [
            tv_episodes.map_episode_response(dict(GOT_S1E1, series_id=1399)),
            None,
        ]

        summary = tv_episodes.sync_episodes(
            [(1399, 1, 1), (1399, 99, 99)],
            self.store,
            skip_fresh=False,
        )

        self.assertEqual(1, summary['synced'])
        self.assertEqual(1, summary['not_found'])
        self.assertEqual(0, summary['errors'])
        self.assertIsNotNone(self.store.get(1399, 1, 1))


class TestTmdbApiTvEpisode(unittest.TestCase):
    @mock.patch('python.lib.tmdbscraper.api_utils.load_info_with_retry')
    @mock.patch('python.lib.tmdbscraper.api_utils.set_headers')
    def test_get_tv_episode__builds_url_and_params(self, _mock_headers, mock_load):
        mock_load.return_value = GOT_S1E1

        result = tmdbapi.get_tv_episode(1399, 1, 1, language='en-US', append_to_response='credits')

        self.assertEqual(GOT_S1E1, result)
        called_url = mock_load.call_args[0][0]
        self.assertIn('/tv/1399/season/1/episode/1', called_url)
        params = mock_load.call_args[1]['params']
        self.assertEqual('en-US', params['language'])
        self.assertEqual('credits', params['append_to_response'])
        self.assertIn('api_key', params)


class TestLoadInfoWithRetry(unittest.TestCase):
    @mock.patch('python.lib.tmdbscraper.api_utils.time.sleep')
    @mock.patch('python.lib.tmdbscraper.api_utils.load_info')
    def test_load_info_with_retry__backs_off_on_429(self, mock_load, mock_sleep):
        from python.lib.tmdbscraper import api_utils

        mock_load.side_effect = [
            {'error': 'remote site unable to fulfill the request\nError code: 429'},
            {'id': 1},
        ]

        result = api_utils.load_info_with_retry('https://example.test')

        self.assertEqual({'id': 1}, result)
        mock_sleep.assert_called_once()
