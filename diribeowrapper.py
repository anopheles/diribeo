# -*- coding: utf-8 -*-

import datetime
import locale

from diribeomodel import Episode, NoConnectionAvailable, series_list

class LibraryWrapper(object):
    def __init__(self):
        self.implementations = [IMDBWrapper(), IMDBWrapper()]

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

    def get_series_from_movie(self, movie):
        for implementation in self.implementations:
            result = implementation.get_series_from_movie(movie)
            if result is not None:
                return result

class IMDBWrapper(object):
    def __init__(self):
        #Import the imdb package.
        import imdb

        #Create the object that will be used to access the IMDb's database.
        self.ia  = imdb.IMDb(loggginLevel = "critical", proxy = "") # by default access the web.
        
        self.identifier = "imdb"        


    def get_episodes(self, imdb_series):
        #Get more information about the series
        self.ia.update(imdb_series)

        #Get informaon about the episodes
        self.ia.update(imdb_series, 'episodes')

        seasons = imdb_series.get('episodes')

        numberofepisodes = imdb_series.get('number of episodes') - 1

        # Import helpers form imdb to sort episodes
        from imdb import helpers

        #Sort Episodes
        helpers.sortedEpisodes(seasons)

        #Ratings
        self.ia.update(imdb_series, 'episodes rating')        
        ratings = imdb_series.get('episodes rating')        

        counter = 1
        for seasonnumber in seasons.iterkeys():
            if type(seasonnumber) == type(1):
                for imdb_episode_number in seasons[seasonnumber]:  
                    imdb_episode = seasons[seasonnumber][imdb_episode_number]
                    date = self.convert_string_to_date(str(imdb_episode.get('original air date')))                   
                    episode = Episode(title = imdb_episode.get('title'), descriptor = [imdb_episode.get('season'), imdb_episode.get('episode')], series = (imdb_series.get('title'), {"imdb" : imdb_series.movieID}), date = date, plot = imdb_episode.get('plot'), identifier = {"imdb" : imdb_episode.movieID}, rating = {"imdb" : self.get_rating(ratings, imdb_episode)}, number = counter)
                    counter += 1
                    yield episode, numberofepisodes

        return


    def convert_string_to_date(self, datestring):
        locale.setlocale(locale.LC_ALL, 'en_US') #TODO
        try:
            return datetime.datetime.strptime(datestring, "%d %B %Y")
        except ValueError:
            try:
                return datetime.datetime.strptime(datestring, "%B %Y")
            except ValueError:
                pass

    def get_more_information(self, series, movie):
        self.ia.update(movie)
        series.identifier = {"imdb" : movie.movieID}
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
                    output.append((movie, movie.get('smart long imdb canonical title'), self.identifier))
            return output
        except IMDbError:
            raise NoConnectionAvailable

    def get_series_from_movie(self, movie):
        """ Checks if the IMDB movie is already present in the series list.
        If it is presents it returns the series object. None otherwise.          
        """
        for series in series_list:
            try:
                if series.identifier["imdb"] == movie.movieID:
                    return series
            except KeyError, TypeError:
                pass

    def get_rating(self, ratings, imdb_episode):
        """private"""
        try:
            for single_rating in ratings:
                if single_rating["episode"] == imdb_episode:
                    return [single_rating["rating"], single_rating["votes"]]                
        except TypeError:
            pass               


library = LibraryWrapper()