# ==============================================================================
# About
# ==============================================================================
#
# streamers.py contains the Stream, Streamer, and Streamers classes
# - Stream is the representation of a livestream or video
# - Streamer is a Twitch streamer
# - Streamers is a collection of streamers and is responsible for all bulk operations like importing/exporting from csv
#

# Imports ----------------------------------------------------------------------

import sys
import csv
import json
import time
import datetime

csv.field_size_limit(sys.maxsize) # <- so csv can load very large fields


# ==============================================================================
# Stream
# ==============================================================================

class Stream():

    def __init__(self, twitch_obj, is_livestream = True):

        # livestreams and videos have different access keys
        date_key = 'started_at' if (is_livestream) else 'created_at'
        views_key = 'viewer_count' if (is_livestream) else 'view_count'

        # convert Twitch's UTC Format to Unix Epoch
        day = twitch_obj[date_key].split("T")[0] # <- we only care about data on the day/month/year level
        epoch = int(datetime.datetime.strptime(day, '%Y-%m-%d').timestamp())

        self.id             = int(twitch_obj['id'])
        self.user_id        = int(twitch_obj['user_id'])
        self.twitch_game_id = int(twitch_obj['game_id']) if ('game_id' in twitch_obj and twitch_obj['game_id'] != '') else 0
        self.game_name      = twitch_obj['game_name'] if ('game_name' in twitch_obj) else ""
        self.language       = twitch_obj['language']
        self.date           = epoch
        self.views          = twitch_obj[views_key]
        self.is_livestream  = is_livestream
        self.title          = twitch_obj['title']


    def print_info(self):
        print("title:", self.title)
        print("id:", self.id, "user:", self.user_id)
        print('game: ', self.twitch_game_id, " - ", self.game_name)
        print("date: ", self.date)
        print("views:", self.views)
        print("livestream: ", self.is_livestream)
        print("-")

# ==============================================================================
# Streamer
# ==============================================================================

class Streamer():

    def __init__(self, streamer_obj, from_csv = False):
        if (from_csv):
            self.id                = int(streamer_obj['id'])
            self.login             = streamer_obj['login']
            self.display_name      = streamer_obj['display_name']
            self.profile_image_url = streamer_obj['profile_image_url']
            self.view_counts       = json.loads(streamer_obj['view_counts'])
            self.description       = streamer_obj['description']
            self.follower_counts   = json.loads(streamer_obj['follower_counts'])
            self.language          = streamer_obj['language']
            self.stream_history    = self.__load_stream_history(streamer_obj['stream_history'])

        else:
            self.id                = int(streamer_obj['id'])
            self.login             = streamer_obj['login']
            self.display_name      = streamer_obj['display_name']
            self.profile_image_url = streamer_obj['profile_image_url']
            self.view_counts       = [ {'views': streamer_obj['view_count'], 'date': int(time.time())} ]
            self.description       = streamer_obj['description']
            self.follower_counts   = streamer_obj['follower_counts'] if ('follower_counts' in streamer_obj) else []
            self.language          = streamer_obj['language'] if ('language' in streamer_obj) else ""
            self.stream_history    = {} # will have format {twitch_game_id: num_times_played}


    # stream history, when JSONified, converts all game_ids into strings, even the ints
    # -> we need to re-intify those game_ids
    def __load_stream_history(self, obj):
        stream_history = {}
        obj = json.loads(obj)
        for key, value in obj.items():
            if (self.__check_if_str_is_int(key)):
                key = int(key)
            stream_history[key] = value
        return stream_history

    def __check_if_str_is_int(self, str):
        try:
            val = int(str)
            return True
        except ValueError:
            return False

    # updates profile information w/ new info from Twitch
    def update(self, streamer_obj):
        self.display_name      = streamer_obj['display_name']
        self.login             = streamer_obj['login']
        self.profile_image_url = streamer_obj['profile_image_url']
        self.description       = streamer_obj['description']
        self.language          = streamer_obj['language'] if ('language' in streamer_obj) else self.language


        # if the most recent view_count is in the last 24 hours, we can just modify that instead of adding a new entry
        current_time = int(time.time())
        yesterday = current_time - (60*60*24)
        if (len(self.get_view_counts_in_range(yesterday, current_time)) > 0):
            self.view_counts[-1]['views'] = streamer_obj['view_count']
            self.view_counts[-1]['date'] = current_time
        else:
            self.view_counts.append({'views': streamer_obj['view_count'], 'date': current_time })


    # adds a new entry to follower_count
    def add_follower_data(self, followers):
        self.follower_counts.append({'followers': followers, 'date': int(time.time())})


    # adds data from a video or livestream
    def add_stream_data(self, stream):

        def get_date_obj(streamed_date):
            return {'streamed': streamed_date, 'scraped': int(time.time())}

        # add game info
        game_key = stream.twitch_game_id if (stream.is_livestream) else stream.game_name
        views_contributed = stream.views if (stream.is_livestream) else 0
        videos_contributed = 0 if (stream.is_livestream) else 1
        last_stream_date, recent_streamed_games = self.get_most_recent_streamed_games()


        if (game_key in self.stream_history):

            self.stream_history[game_key]['videos'] += videos_contributed

            # if the current stream has *just* switched over to this stream, record its views
            if (game_key not in recent_streamed_games):
                self.stream_history[game_key]['dates'].append(get_date_obj(stream.date))
                self.stream_history[game_key]['recent'] = views_contributed
                self.stream_history[game_key]['views'] += views_contributed
            else:
                # if we have already recorded the current stream with this game,
                # -> we only want to update the views contributed if its greater than last time
                if (self.stream_history[game_key]['recent'] < views_contributed):
                    self.stream_history[game_key]['views'] -= self.stream_history[game_key]['recent']
                    self.stream_history[game_key]['views'] += views_contributed
                    self.stream_history[game_key]['recent'] = views_contributed


        else:
            self.stream_history[game_key] = {
                'views': views_contributed,
                'recent': views_contributed,
                'videos': videos_contributed,
                'dates': [get_date_obj(stream.date)]
            }


    # Get ----------------------------------------------------------------------

    # goes through stream_history and returns the streams that were most recently streamed
    # returns as a tuple (date, [list of game_ids])
    def get_most_recent_streamed_games(self):
        latest_date = 0
        game_ids = []
        for game in self.stream_history:
            for date_obj in self.stream_history[game]['dates']:
                if (date_obj['streamed'] > latest_date):
                    latest_date = date_obj['streamed']
                elif (date_obj['streamed'] == latest_date):
                    game_ids.append(game)

        return latest_date, game_ids

    # returns the most recent follower count obj for this streamer
    # -> this should be the last follower_count object in the list, but we will check every case to be safe
    def get_most_recent_follower_count(self):
        if (len(self.follower_counts) == 0):
            return False

        followers = self.follower_counts[0]
        for obj in self.follower_counts:
            if (obj['date'] > followers['date']):
                followers = obj
        return followers

    # returns a tuple ([list of games in livestreams], [list of games in videos])
    def get_games_played(self):
        livestreams, videos = [], []
        for game in self.stream_history:
            if (isinstance(game, int)):
                livestreams.append(game)
            else:
                videos.append(game)
        return livestreams, videos


    # returns all games livestreamed in date range
    def get_games_livestreamed_in_range(self, time1 = 0, time2 = int(time.time())):
        games = []
        for game_id in self.stream_history:
            if (isinstance(game_id, int)):
                for livestream in self.stream_history[game_id]['dates']:
                    if ((livestream['streamed'] >= time1) and (livestream['streamed'] <= time2)):
                        games.append(game_id)
        return games

    # returns all view_counts within date range
    def get_view_counts_in_range(self, time1 = 0, time2 = int(time.time())):
        view_counts = []
        for obj in self.view_counts:
            if ((obj['date'] >= time1) and (obj['date'] <= time2)):
                view_counts.append(obj)
        return view_counts


    # returns self.stream_history, but with only videos
    def get_video_history(self):
        history = {}
        for game in self.stream_history:
            if (isinstance(game, str)):
                history[game] = self.stream_history[game]
        return history

    # returns self.stream_history, but with only livestreams
    def get_livestream_history(self):
        history = {}
        for game in self.stream_history:
            if (isinstance(game, int)):
                history[game] = self.stream_history[game]
        return history

    def get_twitch_url(self):
        return 'https://www.twitch.tv/' + self.login


    def to_dict(self):
        obj = {
            'id': self.id,
            'login': self.login,
            'display_name': self.display_name,
            'profile_image_url': self.profile_image_url,
            'view_counts': self.view_counts,
            'description': self.description,
            'follower_counts': self.follower_counts,
            'language': self.language,
            'stream_history': self.stream_history
        }
        return obj

    def to_exportable_dict(self):
        obj = self.to_dict()
        obj['stream_history'] = json.dumps(obj['stream_history'])
        obj['view_counts'] = json.dumps(obj['view_counts'])
        obj['follower_counts'] = json.dumps(obj['follower_counts'])
        return obj

# ==============================================================================
# Streamers
# ==============================================================================


class Streamers():

    def __init__(self, filename = False):
        self.streamers = {}
        if (filename):
            self.load_from_csv(filename)

    # sets streamers to be empty, effectively wiping the Streamers object
    def reset(self):
        self.streamers = {}

    # get ----------------------------------------------------------------------

    # returns a specified streamer
    def get(self, streamer_id):
        if (streamer_id in self.streamers):
            return self.streamers[streamer_id]
        return False

    # returns a list of all streamer IDs in collection
    # this list is sorted so that it will return consistent results
    def get_ids(self):
        ids = list(self.streamers.keys())
        ids.sort()
        return ids

    # returns a list of streamer IDs that do not have any streamer data on record
    def get_ids_with_no_video_data(self):
        ids = []
        for id, streamer in self.streamers.items():
            livestreamed_games, video_games = streamer.get_games_played()
            if (len(video_games) == 0):
                ids.append(id)

        ids.sort()
        return ids


    # returns a list of all streamer IDs that do not have follower data from the last day
    def get_ids_with_missing_follower_data(self):

        ids = []
        current_time = int(time.time()) # <- this is in seconds
        day_boundary = current_time - 60 * 60 * 24 # <- seconds*minutes*hours ~ seconds in a day

        for id, streamer in self.streamers.items():
            follower_count = streamer.get_most_recent_follower_count()
            if (follower_count == False):
                ids.append(id)
            elif (follower_count['date'] < day_boundary):
                ids.append(id)

        ids.sort()
        return ids


    # returns all streamers who livestreamed within a range of times
    def get_ids_who_livestreamed_in_range(self, time1, time2):
        ids = []
        for id, streamer in self.streamers.items():
            if (len(streamer.get_games_livestreamed_in_range(time1, time2)) > 0):
                ids.append(id)
        return ids

    # returns all streamers with view_counts from within a range of times
    def get_ids_with_view_counts_in_range(self, time1, time2):
        ids = []
        for id, streamer in self.streamers.items():
            if (len(streamer.get_view_counts_in_range(time1, time2)) > 0):
                ids.append(id)
        return ids



    # insert -------------------------------------------------------------------

    # inserts a new streamer into the collection
    def add_or_update_streamer(self, twitch_obj):
        streamer_id = twitch_obj['user_id'] if ('user_id' in twitch_obj) else twitch_obj['id']
        streamer_id = int(streamer_id) if (not isinstance(streamer_id, int)) else streamer_id
        if (streamer_id not in self.streamers):
            self.streamers[streamer_id] = Streamer(twitch_obj)
        else:
            self.streamers[streamer_id].update(twitch_obj)

    # for a specific streamer, add video/livestream data
    def add_stream_data(self, stream):
        if (stream.user_id in self.streamers):
            self.streamers[stream.user_id].add_stream_data(stream)

    # for a specific streamer, add a new follower count to streamer.follower_counts
    def add_follower_data(self, streamer_id, followers):
        if (streamer_id in self.streamers):
            self.streamers[streamer_id].add_follower_data(followers)


    # File I/O -----------------------------------------------------------------

    def export_to_csv(self, filename):
        fieldnames = [
            'id', 'login', 'display_name', 'profile_image_url', 'view_counts', 'description',
            'follower_counts', 'language', 'stream_history'
        ]
        filename = filename if ('.csv' in filename) else filename + '.csv'
        with open(filename, 'w') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for streamer_id, streamer in self.streamers.items():
                writer.writerow(streamer.to_exportable_dict())

    def load_from_csv(self, filename):
        filename = filename if ('.csv' in filename) else filename + '.csv'
        try:
            with open(filename) as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    streamer = Streamer(row, True)
                    self.streamers[streamer.id] = streamer
        except IOError:
            print(filename, "does not exist yet")

    # Data Validation ----------------------------------------------------------

    # compares this Streamers object with another Streamers object
    # returns True if they point at the exact same streamers
    def check_if_streamer_collection_same(self, streamers2):

        # case 0: there are an uneven number of streamers in each collection
        if (len(self.streamers) != len(streamers2.streamers)):
            print('checkpoint a')
            return False

        for streamer_id in self.streamers:

            streamer1 = self.get(streamer_id)
            streamer2 = streamers2.get(streamer_id)

            # case 1: 1 collection has a specified streamer but the other doesn't
            if ((streamer1 == False) or (streamer2 == False)):
                print('checkpoint b')
                return False

            obj1 = streamer1.to_dict()
            obj2 = streamer2.to_dict()

            # case 2: the collection's Streamer objects hav ea different number of parameters
            if (len(obj1) != len(obj2)):
                print('checkpoint c')
                return False

            for key in obj1:
                val1 = obj1[key]
                if (key not in obj2): # case 3: one Game has a parameter that the other lacks
                    print('checkpoint d')
                    return False
                val2 = obj2[key]

                if (type(val1) != type(val2)): # case 4: the type of parameters aren't the same between Streamers
                    print('checkpoint e')
                    return False

                # case 5: parameter values just aren't the same
                if (key == 'stream_history'): # <- this will be the 'stream_history' parameter
                    if (not self.__check_if_stream_histories_same(val1, val2)):
                        return False
                elif (key == 'view_counts'):
                    if (not self.__check_if_view_counts_same(val1, val2)):
                        return False
                elif (key == 'follower_counts'):
                    if (not self.__check_if_followers_same(val1, val2)):
                        return False
                else:
                    if (val1 != val2):
                        print('checkpoint m')

        return True


    # returns True if the two given stream history objects are the same
    # - stream history object has form { game_id: {'views': INT, 'videos': INT, dates: [DATE_OBJ]}}
    # where
    # - DATE_OBJ = {'scraped': INT_DATE, 'streamed': INT_DATE}
    def __check_if_stream_histories_same(self, sh1, sh2):

        # make sure stream history objects are dicts
        if ((not isinstance(sh1, dict)) or (not isinstance(sh2, dict))):
            return False

        # make sure stream histories have the same number of games
        if (len(sh1) != len(sh2)):
            return False

        # iterate over all games in stream history
        for game_id in sh1:

            # make sure both stream history objects have the same game
            if (game_id not in sh2):
                return False

            # check to see if the INT attributes are the same
            if (sh1[game_id]['views'] != sh2[game_id]['views']):
                return False
            if (sh1[game_id]['videos'] != sh2[game_id]['videos']):
                return False

            # check to make sure the date objects are the same
            if (len(sh1[game_id]['dates']) != len(sh2[game_id]['dates'])):
                return False

            for i in range(len(sh1[game_id]['dates'])):
                date_obj1 = sh1[game_id]['dates'][i]
                date_obj2 = sh2[game_id]['dates'][i]

                if (date_obj1['streamed'] != date_obj2['streamed']):
                    return False
                if (date_obj1['scraped'] != date_obj2['scraped']):
                    return False

        return True

    # returns True if two view_counts lists are the same
    # - view_counts has form: [{'views': INT, 'date': INT_DATE}]
    def __check_if_view_counts_same(self, views1, views2):

        # make sure both views objects are lists
        if ((not isinstance(views1, list)) or (not isinstance(views2, list))):
            return False

        # make sure both objects have the same number of views
        if (len(views1) != len(views2)):
            return False

        # iterate over all views objects to make sure they are all the same
        for i in range(len(views1)):
            obj1 = views1[i]
            obj2 = views2[i]

            if (obj1['views'] != obj2['views']):
                return False
            if (obj1['date'] != obj2['date']):
                return False
        return True


    # returns True if follower counts are the same
    # - followers have form [{'followers': INT, 'date': INT_DATE}]
    def __check_if_followers_same(self, followers1, followers2):

        # make sure both objects are lists
        if ((not isinstance(followers1, list)) or (not isinstance(followers2, list))):
            return False

        # make sure both have the same number of followers objects
        if (len(followers1) != len(followers2)):
            return False

        # iterate over all followers objects to make sure they are the same
        for i in range(len(followers1)):
            obj1 = followers1[i]
            obj2 = followers2[i]

            if (obj1['followers'] != obj2['followers']):
                return False
            if (obj1['date'] != obj2['date']):
                return False
        return True
