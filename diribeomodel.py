# -*- coding: utf-8 -*-
'''
Created on 05.07.2010

@author: anopheles
'''

import datetime
import json
import shutil
import os

from PyQt4 import QtCore


class MovieClip(object):
    def __init__(self, filepath, identifier = None, filesize = None, checksum = None, thumbnails = None):
        self.filepath = filepath
                    
        self.identifier = identifier 
        self.checksum = checksum
            
        if filesize is None:
            self.get_filesize()
        else:
            self.filesize = filesize
        
        if thumbnails is None:
            thumbnails = []    
        self.thumbnails = thumbnails
        
    def get_filename(self):
        return os.path.basename(self.filepath)    
    
    def get_thumbnails(self):
        """ This function gathers the thumbnails and adds them to the dedicated thumnails list"""
        pass

    def merge(self, other):
        """ This function merges the current movie clip object with another one.
        The current movie clip will be updated.
        
        To be able to merge two movie clips both movie clips must have the same checksum.
        If this is not the case a TypeError exception is raised.
        
        """
        if self == other:
            self.identifier.update(other.identifier)
        else:
            raise TypeError, "You're trying to merge two movie clips which don't have the same checksum"
        
    def get_filesize(self):
        try:
            return self.filesize
        except AttributeError:
            """This function calculates the file size in bytes of the given file and returns the result"""
            assert os.path.isfile(self.filepath), self.filepath
    
            self.filesize = os.path.getsize(self.filepath)
            return self.filesize

    
    def get_folder(self):
        if os.path.isfile(self.filepath):
            return os.path.dirname(self.filepath)

    def delete_file_in_deployment_folder(self, series_name):
        if os.path.isfile(self.filepath):
            os.remove(self.filepath)
    
    def __eq__(self, other):
        if self.checksum == other.checksum:
            return True
    
    def __hash__(self):
        return hash(self.checksum)
        
    def __repr__(self):
        return "M(" + self.filepath + ")"


class NoConnectionAvailable(Exception):
    def __init__(self):
        pass


class DownloadedSeries(object):
    def __init__(self, title, internal_representation, identifier):
        self.title = title
        self.internal_representation = internal_representation
        self.identifier = identifier
        
class MovieClipAssociation(object):
    INVALID_FILE, ASSOCIATION_FOUND, ASSOCIATION_GUESSED, ALREADY_EXISTS = range(4)
    
    def __init__(self, filepath):
        self.filepath = filepath
        self.skip = False
        self.movieclip = None
        self.episode_scores_list = None
        self.episode_scores_list_reference = 0
        self.message = None


    def get_associated_episode_score(self):
        return self.episode_scores_list[self.episode_scores_list_reference]


def SeriesOrganizerDecoder(dct):
    if '__date__' in dct:
        return datetime.date.fromordinal(dct["ordinal"])

    if '__episode__' in dct:
        return Episode(title = dct["title"], descriptor = dct["descriptor"], series = dct["series"], plot = dct['plot'], date = dct["date"], identifier = dct["identifier"], rating = dct["rating"], director = dct["director"], genre = dct["genre"], runtime = dct["runtime"], seen_it = dct["seen_it"], number = dct["number"])

    if '__series__' in dct:
        return Series(dct["title"], identifier = dct["identifier"], episodes = dct["episodes"], rating = dct["rating"], director = dct["director"], genre = dct["genre"], date = dct["date"])

    if '__movieclip__' in dct:        
        return MovieClip(dct['filepath'], identifier = dct['identifier'], filesize = dct['filesize'], checksum = dct['checksum'], thumbnails = dct["thumbnails"])
    
    if '__movieclips__' in dct:        
        return MovieClipManager(dictionary = dct['dictionary'])
    
    if '__settings__' in dct:
        return Settings(settings = dct['settings'])
    
    if '__set__' in dct:
        return set(dct['contents'])
    
    return dct


class SeriesOrganizerEncoder(json.JSONEncoder):
    def default(self, obj):
        
        if isinstance(obj, Episode):
            return { "__episode__" : True, "title" : obj.title, "descriptor" : obj.descriptor, "series" : obj.series, "plot" : obj.plot, "date" : obj.date, "identifier" : obj.identifier, "rating" : obj.rating, "director" : obj.director, "runtime" : obj.runtime, "genre" : obj.genre, "seen_it" : obj.seen_it, "number" : obj.number}

        if isinstance(obj, datetime.date):
            return { "__date__" : True, "ordinal" : obj.toordinal()}

        if isinstance(obj, Series):
            return { "__series__" : True, "title" : obj.title, "episodes" : obj.episodes, "identifier" : obj.identifier, "rating" : obj.rating,  "director" : obj.director, "genre" : obj.genre, "date" : obj.date}

        if isinstance(obj, MovieClip):
            return { "__movieclip__" : True, "filepath" : obj.filepath, "filesize" : obj.filesize, "checksum" : obj.checksum, "identifier" : obj.identifier, "thumbnails" : obj.thumbnails}        
        
        if isinstance(obj, Settings):
            return { "__settings__" : True, "settings" : obj.settings} 

        if isinstance(obj, MovieClipManager):
            return { "__movieclips__" : True, "dictionary" : obj.dictionary}                
        
        if isinstance(obj, set):
            return { "__set__" : True, "contents" : list(obj)}
        
        if isinstance(obj, QtCore.QString):
            return unicode(obj)        
        
        return json.JSONEncoder.default(self, obj)

class Settings(object):
    def __init__(self, settings = None):
        
        if settings == None:
            self.settings = {"copy_associated_movieclips" : True, 
                             "deployment_folder" : os.path.join(self.get_user_dir(),"Series"),
                             "automatic_thumbnail_creation" : False,
                             "show_all_movieclips" : True,
                             "normalize_names" : True,
                             "thumbnail_folder" : os.path.join(self.get_user_dir(),"Series",".thumbnails"),
                             "hash_movieclips" : True,
                             "number_of_thumbnails" : 8}
        else:
            self.settings = settings      


        self.valid_extensions = ("mkv", "avi", "mpgeg", "mpg", "wmv", "mp4", "mov")

    def get(self, attribute_name):
        try:
            return self.settings[attribute_name]
        except KeyError:
            pass

    def get_thumbnail_folder(self):        
        thumbnail_folder = os.path.join(os.getcwd(), self.settings["thumbnail_folder"])
        if not os.path.exists(thumbnail_folder):
            os.makedirs(thumbnail_folder)
        
        return thumbnail_folder


    def get_normalized_filename(self, filename, episode):
        name, ext = os.path.splitext(filename)
        return episode.get_normalized_name() + ext
    
    
    def get_unique_filename(self, filepath, episode):
        
        directory, filename = os.path.split(filepath)
                
        if self.settings["normalize_names"]:
            filename = self.get_normalized_filename(filename, episode)
           
        return self.get_collision_free_filename(os.path.join(directory, filename))

    def get_collision_free_filename(self, filepath):
        
        directory, filename = os.path.split(filepath)
        
        if os.path.isfile(filepath):
            #Collision detected:            
            split = os.path.splitext(filename)            
            index = 1 
            while(os.path.isfile(os.path.join(directory, filename))):
                filename = split[0] + " " + str(index) + split[1]
                index += 1
        return filename
            

    def get_user_dir(self):
        ''' Returns the user/Home directory of the user running this application. '''     
        return os.path.expanduser("~")
 

    def is_valid_file_extension(self, filepath):
        ''' Checks if the given filepath's filename has a proper movie clip extension ''' 
        filename = os.path.basename(filepath)
        name, ext = os.path.splitext(filename)
        
        if ext.lower().endswith(self.valid_extensions):
            return True


    def calculate_filepath(self, episode, filename, normalize = True):
        ''' Calculates the destination filepath of a given episode '''
        if self.settings["normalize_names"] and normalize:
            filename = self.get_normalized_filename(filename, episode)
        return os.path.join(self.settings["deployment_folder"], episode.series[0], "Season " + str(episode.descriptor[0]), filename)


    def move_file_to_folder_structure(self, episode, filepath, new_filename = None):
        ''' This method is responsible for moving the given file, specified via filepath, to the calculated destination.
            It is also possible to define a new filename with the help of the new_filename parameter.
        '''
        
        if new_filename is not None:
            filename = new_filename
        else:
            filename = os.path.basename(filepath)
        
        # Force normalization off
        destination = self.calculate_filepath(episode, filename, normalize = False)

        directory = os.path.dirname(destination)
        
        if not os.path.exists(directory):
            os.makedirs(directory) 
        
        # Copy / Move movie clip
        if self.settings["copy_associated_movieclips"]:                
            shutil.copyfile(filepath, destination)
        else:
            shutil.move(filepath, destination)


class Series(object):
    def __init__(self, title, identifier = None, episodes = None, rating = None, director = "", genre = "", date = ""):
        self.title = title

        if episodes == None:
            episodes = []
            
        if identifier == None:
            identifier = {}

        self.episodes = episodes
        self.rating = rating
        self.identifier = identifier
        self.director = director
        self.genre = genre
        self.date = date
        self.season = {}
    
    def __getitem__(self, key):
        ''' Returns the n-th episode of the series '''
        return self.episodes[key]

    def __len__(self):
        ''' Returns the number of episodes '''
        return len(self.episodes)

    def __repr__(self):
        return "S(" + self.title + " E: " + str(len(self.episodes)) + ")"

    def get_seasons(self):
        ''' Returns a dictionary of seasons. Each season contains a list of episodes '''
        try:
            return self.seasons
        except AttributeError:
            self.seasons = {}

            for episode in self.episodes:
                try:
                    self.seasons[episode.descriptor[0]].append(episode)
                except KeyError:
                    self.seasons[episode.descriptor[0]] = []
                    self.seasons[episode.descriptor[0]].append(episode)

            return self.seasons

    def accumulate_episode_count(self, season):
        ''' This function adds all the preceeding episodes of the given season
        and returns the accumulated value '''

        seasons = self.get_seasons()        
        accumulated_sum = 0
        for index, seasonnumber in enumerate(seasons):
            if index - 1 == season:
                break
            accumulated_sum += len(seasons[seasonnumber])

        return accumulated_sum

    def get_movieclips(self):
        return []
        
    def get_identifier(self):
        return self.identifier.items()[0]

class Episode(object):
    def __init__(self, title = "", descriptor = None, series = "", date = None, plot = "", identifier = None, rating = None, director = "", runtime = "", genre = "", seen_it = False, number = 0):
        
        self.title = title
        self.descriptor = descriptor
        self.series = series
        self.plot = plot
        self.date = date
        self.identifier = identifier
        self.rating = rating
        self.director = director
        self.runtime = runtime
        self.genre = genre
        self.seen_it = seen_it
        self.number = number
        
        if rating is None:
            self.rating = []


    def __repr__(self):
        return "E(" + str(self.series[0]) + " - " + str(self.title) + " " + str(self.descriptor[0]) + "x" + str(self.descriptor[1]) +  " " + str(self.date) + ")"

    def __cmp__(self, other):
        try:
            other = other.date
        except (TypeError, AttributeError):
            pass
        return cmp(self.date, other)

    def __eq__(self, other):
        return self.title == other.title and self.descriptor == other.descriptor
    
    
    def get_series(self):
        for series in series_list:
            if series.identifier == self.series[1]:
                return series
    
    def get_descriptor(self):
        return str(self.descriptor[0]) + "x" + str('%0.2d' % self.descriptor[1])

    def get_alternative_descriptor(self):
        return "S" + str('%0.2d' % self.descriptor[0]) + "E" + str('%0.2d' % self.descriptor[1])

    
    def get_thumbnails(self):
        thumbnail_list = []
        for movieclip in self.get_movieclips():
            thumbnail_list += movieclip.thumbnails
        return thumbnail_list
    
    def get_movieclips(self):
        try:
            return movieclips[self.get_identifier()]
        except KeyError:
            return [] #return an empty list    
    
    def get_normalized_name(self):
        return self.series[0] + " " + self.get_descriptor() + " - " + self.title
    
    def get_alternative_name(self):
        return self.series[0] + " " + self.get_alternative_descriptor()
    
    def get_identifier(self):
        # Use the first key as unique identifier. Note that this is propably not a good idea!
        return self.identifier.items()[0]
        
    def get_ratings(self):
        return_text = ""
        for rating in self.rating:
            try:
                return_text = str(rating).upper() + ": " + str(self.rating[rating][0]) + " (" + str(self.rating[rating][1]) + ")\n" + return_text
            except TypeError:
                pass
        return return_text 

class MovieClipManager(object):
    def __init__(self, dictionary = None):
        if dictionary == None:
            self.dictionary = {"imdb" : {}, "tvrage" : {}} #TODO  
        else:
            self.dictionary = dictionary

    def __getitem__(self, identifier):
       
        implementation, key = identifier
        try:            
            return self.dictionary[implementation][key]
        except KeyError:
            pass
            
        return [] # Returns an empty list, to produce a empty iterator

    
    def get_episode_dict_with_matching_checksums(self, checksum):
        ''' This function searches for the given checksum in the internal data structures.
            It returns two lists as a tuple. The first beign a list of episodes. The second
            beign a list of movie clips which match the checksum.
        '''
        
        episode_dict = {} # episode are keys, movieclips are values
        
        for implementation in self.dictionary:
            for key in self.dictionary[implementation]:
                for movieclip in self.dictionary[implementation][key]:
                    if movieclip.checksum == checksum:
                        episode_dict[self.from_movieclip_to_episode(movieclip)] = movieclip 
                       
        return episode_dict
    
    
    def from_movieclip_to_episode(self, movieclip):
        ''' This function searches through the series_list and returns the 
            first episode which is associated to the given movie clip
        '''        
        for series in series_list:
            for episode in series.episodes:
                if episode.identifier == movieclip.identifier:
                    return episode
                

    def check_unique(self, movieclip, identifier):
        ''' Checks if the given movie clip hasn't been assigned to a different epsiode '''
        
        implementation, key = identifier
        for another_key in self.dictionary[implementation]:
            if another_key != key:
                if movieclip in self.dictionary[implementation][another_key]:
                    return False
        return True
        
    def add(self, movieclip):
        implementation, key = movieclip.identifier.items()[0]       
        try:
            self.dictionary[implementation][key].append(movieclip)
        except KeyError:           
            self.dictionary[implementation][key] = []
            self.dictionary[implementation][key].append(movieclip) 

    def remove(self, movieclip, identifier):
        implementation, key = identifier
        self.dictionary[implementation][key].remove(movieclip)

    def __iter__(self):
        return self.dictionary.iteritems()

def save_configs():
    save_movieclips()
    save_series()
    save_settings()


def load_series():
    return load_file("series.json", [])    
    
def load_movieclips():
    return load_file("movieclips.json", MovieClipManager())

def save_series():
    save_file("series.json", series_list)

def save_movieclips():
    save_file("movieclips.json", movieclips)

def load_settings():
    return load_file("settings.json", Settings())

def save_settings():
    save_file("settings.json", settings)


def save_file(filename, contents):
    with open(filename, "w") as f:
        f.write(json.dumps(contents, sort_keys = True, indent = 4, cls = SeriesOrganizerEncoder, encoding = "utf-8"))
    f.close()     

def load_file(filename, default_value):   
    if os.path.exists(filename):
        with open(filename, "r") as f:
            filecontents = f.read()
        f.close() 
        try:
            return json.loads(filecontents, object_hook = SeriesOrganizerDecoder, encoding = "utf-8")
        except ValueError: 
            return default_value
    
    return default_value  


settings = load_settings()
series_list = load_series()
movieclips = load_movieclips()
