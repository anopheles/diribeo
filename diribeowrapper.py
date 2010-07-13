# -*- coding: utf-8 -*-

import datetime
import tvrage.api

from diribeomodel import Episode, NoConnectionAvailable, series_list, DownloadedSeries

class LibraryWrapper(object):
    def __init__(self):
        self.implementations = [TVRageWrapper(), IMDBWrapper()]

    def get_episodes(self, identifier, implementation_identifier):
        for implementation in self.implementations:
            if implementation.identifier == implementation_identifier:
                return implementation.get_episodes(identifier)
        
    def get_more_information(self, series, movie, implementation_identifier):
        for implementation in self.implementations:
            if implementation.identifier == implementation_identifier:
                return implementation.get_more_information(series, movie)

    def search_movie(self, title):
        output = []
        for implementation in self.implementations:
            output += implementation.search_movie(title)
        return output

    def get_series_from_identifier(self, identifier):
        for series in series_list:
            try:
                if series.identifier == identifier:
                    return series
            except KeyError, TypeError:
                pass


class SourceWrapper(object):
    def __init__(self):
        self.month_lookup = { "January" : 1,
                              "February" : 2,
                              "March": 3, 
                              "April" : 4, 
                              "May" : 5,
                              "June" : 6,
                              "July" : 7,
                              "August" : 8,
                              "September" : 9,
                              "October" : 10,
                              "November" : 11,
                              "December" : 12}
    
    def get_episodes(self, implementation):
        raise NotImplementedError
    
    def get_more_information(self, series, movie):
        raise NotImplementedError
    
    def search_movie(self, title):
        raise NotImplementedError

class TVRageWrapper(SourceWrapper):
    def __init__(self):
        SourceWrapper.__init__(self)
        self.identifier = "tvrage"
        
    def get_episodes(self, tvrage_series):
        episode_count = self.__get_episode_count(tvrage_series.episodes)
        
        counter = 1
        for season_number in tvrage_series.episodes:
            for episode_number in tvrage_series.episodes[season_number]:
                tvrage_episode = tvrage_series.episodes[season_number][episode_number]
                episode = Episode(title = tvrage_episode.title, 
                                  descriptor = [season_number, episode_number], 
                                  series = (tvrage_series.showname, {self.identifier: tvrage_series.showid}), 
                                  identifier = {self.identifier : str(tvrage_series.showid) + "E%0.3d" % counter}, 
                                  number = counter, 
                                  plot = tvrage_episode.summary, 
                                  date = tvrage_episode.airdate)
                counter += 1
                yield episode, episode_count
    
    def __get_episode_count(self, episodes):
        count = 0
        for season_number in episodes:
            count += len(episodes[season_number]) 
        return count
        
    def get_more_information(self, series, movie):
        series.genre = "\n".join(movie.genres)

    def search_movie(self, title):
        output = []
        
        search = tvrage.api.search(str(title))
        for showinfo in search:
            output.append(DownloadedSeries(showinfo.showname, showinfo, {self.identifier : showinfo.showid}))
        return output


        
class IMDBWrapper(SourceWrapper):
    def __init__(self):
        SourceWrapper.__init__(self)
        # Import the imdb package.
        import imdb

        # Create the object that will be used to access the IMDb's database.
        self.ia  = imdb.IMDb(loggginLevel = "critical", proxy = "") # by default access the web.
        
        self.identifier = "imdb"        


    def get_episodes(self, imdb_series):
        # Get more information about the series
        self.ia.update(imdb_series)

        # Get informaon about the episodes
        self.ia.update(imdb_series, 'episodes')

        seasons = imdb_series.get('episodes')

        numberofepisodes = imdb_series.get('number of episodes') - 1

        # Import helpers form imdb to sort episodes
        from imdb import helpers

        # Sort Episodes
        helpers.sortedEpisodes(seasons)

        # Ratings
        self.ia.update(imdb_series, 'episodes rating')        
        ratings = imdb_series.get('episodes rating')        

        counter = 1
        for seasonnumber in seasons.iterkeys():
            if type(seasonnumber) == type(1):
                for imdb_episode_number in seasons[seasonnumber]:  
                    imdb_episode = seasons[seasonnumber][imdb_episode_number]
                    date = self.__convert_string_to_date(str(imdb_episode.get('original air date')))                   
                    episode = Episode(title = imdb_episode.get('title'), 
                                      descriptor = [imdb_episode.get('season'), imdb_episode.get('episode')], 
                                      series = (imdb_series.get('title'), {"imdb" : imdb_series.movieID}), 
                                      date = date, plot = imdb_episode.get('plot'), 
                                      identifier = {"imdb" : imdb_episode.movieID}, 
                                      rating = {"imdb" : self.__get_rating(ratings, imdb_episode)}, 
                                      number = counter)
                    counter += 1
                    yield episode, numberofepisodes

    def __convert_string_to_date(self, datestring):
        splitted_datestring = datestring.split()
        try:
            day = int(splitted_datestring[-3])
        except IndexError:
            day = 1
        try:
            month = self.month_lookup[splitted_datestring[-2]]
        except IndexError:
            month = 1
        
        try:    
            year = int(splitted_datestring[-1])
        except ValueError:
            return None

          
        return datetime.date(year, month, day)

    def get_more_information(self, series, movie):
        self.ia.update(movie)
        series.rating = {"imdb" : [movie.get("rating"), movie.get("votes")]}
        try:
            series.director = "\n".join(person['name'] for person in movie.get("director"))
        except TypeError:
            pass
        series.genre = "\n".join(movie.get("genre"))
        series.date = movie.get('year')

    def search_movie(self, title):
        from imdb import IMDbError 
        try: 
            output = []
            query = self.ia.search_movie(title)
            for movie in query:
                if movie.get('kind') == "tv series":
                    output.append(DownloadedSeries(movie.get('smart long imdb canonical title'), movie, {self.identifier : movie.movieID}))
            return output
        except IMDbError:
            raise NoConnectionAvailable
    
    def __get_rating(self, ratings, imdb_episode):
        try:
            for single_rating in ratings:
                if single_rating["episode"] == imdb_episode:
                    return [single_rating["rating"], single_rating["votes"]]                
        except TypeError:
            pass               


library = LibraryWrapper()