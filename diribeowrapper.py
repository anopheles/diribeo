# -*- coding: utf-8 -*-

import datetime
import tvrage.api

from diribeomodel import Episode, Series, NoInternetConnectionAvailable, series_list, DownloadedSeries, settings, DownloadError

class LibraryWrapper(object):
    def __init__(self):
        implementation_list = [IMDBWrapper(), TVRageWrapper()]
        self.implementations = dict([(implementation.identifier,implementation) for implementation in implementation_list])
        
    def get_episodes(self, identifier, implementation_identifier):
        return self.implementations[implementation_identifier].get_episodes(identifier)
        
    def get_more_information(self, series, movie, implementation_identifier):
        return self.implementations[implementation_identifier].get_more_information(series, movie)

    def update_movie(self, movie):
        return self.implementations[movie.get_implementation_identifier()].update_movie(movie)
    
    def search_movie(self, title, sources):
        output = []
        for implementation in self.implementations:
            if sources[implementation] is not False:
                output += self.implementations[implementation].search_movie(title)
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
    
    def update_movie(self, movie):
        if isinstance(movie, Series):
            self.update_series(movie, merge_policy=settings.get("merge_policy_series"))
        else:
            self.update_episode(movie, merge_policy=settings.get("merge_policy_episode"))
    
    def update_episode(self, episode, merge_policy=None):
        raise NotImplementedError
    
    def update_series(self, series, merge_policy=None):
        raise NotImplementedError
    
    def get_URL(self, movie):
        raise NotImplementedError

class TVRageWrapper(SourceWrapper):
    def __init__(self, activated=False):
        SourceWrapper.__init__(self)
        self.identifier = "tvrage"
        self.image = "images/tvrage.png"
        self.activated = activated        
        
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
        
        try:
            search = tvrage.api.search(str(title))
            for showinfo in search:
                output.append(DownloadedSeries(showinfo.showname, showinfo, {self.identifier : showinfo.showid}))
            return output
        except tvrage.api.NoInternetConnectionAvailable:
            raise NoInternetConnectionAvailable

    def update_episode(self, episode, merge_policy=None):
        pass
    
    def update_series(self, series, merge_policy=None):
        pass
    
        
class IMDBWrapper(SourceWrapper):
    def __init__(self, activated=True):
        SourceWrapper.__init__(self)
        # Import the imdb package.
        import imdb

        # Create the object that will be used to access the IMDb's database.
        self.ia  = imdb.IMDb(loggginLevel="critical") # by default access the web.
        
        self.identifier = "imdb"
        self.image = "images/imdb.png"
        self.activated = activated          


    def get_episodes(self, imdb_series):
        # Get more information about the series
        self.ia.update(imdb_series)

        # Get informaon about the episodes
        self.ia.update(imdb_series, 'episodes')

        seasons = imdb_series.get('episodes')
        
        try:
            numberofepisodes = imdb_series.get('number of episodes') - 1
        except TypeError:
            raise DownloadError

        # Import helpers form imdb to sort episodes
        from imdb import helpers

        # Sort Episodes
        helpers.sortedEpisodes(seasons)

        # Ratings
        self.ia.update(imdb_series, 'episodes rating')
        ratings = imdb_series.get('episodes rating')

        counter = 0
        for seasonnumber in seasons.iterkeys():
            if type(seasonnumber) == type(1):
                for imdb_episode_number in seasons[seasonnumber]:  
                    imdb_episode = seasons[seasonnumber][imdb_episode_number]
                    counter += 1
                    yield self.__imdb_episode_to_episode(imdb_episode, imdb_series = imdb_series, ratings = ratings, counter = counter), numberofepisodes

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


    def update_series(self, old_series, merge_policy=None):
        imdb_series = self.ia.get_movie(old_series.get_identifier()[1])
        new_series = Series(imdb_series.get('title'), identifier = old_series.identifier)
        
        for episode, episode_count in self.get_episodes(imdb_series):
            new_series.episodes.append(episode) 
        old_series.merge(new_series, merge_policy=merge_policy)
    
    def update_episode(self, old_episode, merge_policy=None):
        imdb_episode = self.ia.get_movie(old_episode.get_identifier()[1])
        new_episode = self.__imdb_episode_to_episode(imdb_episode)
        old_episode.merge(new_episode, merge_policy=merge_policy)
        
    
    def __imdb_episode_to_episode(self, imdb_episode, imdb_series = None, ratings = None, counter = None):
            
            if imdb_series is not None:
                series = (imdb_series.get('title'), {"imdb" : imdb_series.movieID})                
            else:
                series = None
                            
                               
            if ratings is not None:                
                rating = {"imdb" : self.__get_rating(ratings, imdb_episode)}
            else:
                rating = {"imdb" : [imdb_episode.get("rating"), imdb_episode.get("votes")]}
                
                               
            date = self.__convert_string_to_date(str(imdb_episode.get('original air date')))
            
            plot = imdb_episode.get('plot')
            if isinstance(plot, list):
                plot = "".join(plot)
            
            if plot is None:
                plot = ""
            
            
            episode = Episode(title = imdb_episode.get('title'), 
                              descriptor = [imdb_episode.get('season'), imdb_episode.get('episode')], 
                              series = series, 
                              date = date, 
                              plot = plot, 
                              identifier = {"imdb" : imdb_episode.movieID}, 
                              rating = rating, 
                              number = counter)
            return episode
        

    def get_more_information(self, series, movie):
        self.ia.update(movie)
        series.rating = {"imdb" : [movie.get("rating"), movie.get("votes")]}
        try:
            series.director = "\n".join(person['name'] for person in movie.get("director"))
        except TypeError:
            pass
        series.genre = "\n".join(movie.get("genre"))
        series.date = movie.get('year')
        try:
            series.plot = "\n".join(movie.get('plot'))
        except TypeError:
            pass

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
            raise NoInternetConnectionAvailable
    
    def __get_rating(self, ratings, imdb_episode):
        try:
            for single_rating in ratings:
                if single_rating["episode"] == imdb_episode:
                    return [single_rating["rating"], single_rating["votes"]]                
        except TypeError:
            pass               

    def get_URL(self, movie):
        id = movie.identifier.values()[0]
        return "http://www.imdb.com/title/tt"+id+"/"

library = LibraryWrapper()