# -*- coding: utf-8 -*-

import datetime
import json
import shutil
import os
import sys

from PyQt4 import QtCore


class MergePolicy(object):  
    OVERWRITE = 0
    MORE_INFO = 1

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

    def delete_file_in_deployment_folder(self):
        ''' Deletes the file in the deplyoment folder '''
            
        if os.path.isfile(self.filepath):
            os.remove(self.filepath)    
    
    def delete_thumbnails(self):
        ''' Delete the generated thumbnails '''                
        for filepath, timecode in self.thumbnails:
            os.remove(filepath)
            
        self.thumbnails = []
    
    def __eq__(self, other):
        if self.checksum == other.checksum and self.filesize == other.filesize:
            return True

    def __repr__(self):
        return "M(" + self.filepath + ")"


class NoInternetConnectionAvailable(Exception): pass


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
        self.episode_score_information = {"mean" : 0, "median" : 0}
        self.message = None


    def get_associated_episode_score(self):
        return self.episode_scores_list[self.episode_scores_list_reference]


    def __str__(self):
        return "MovieClipAssociation( " + self.get_associated_episode_score()+ " )" 


def SeriesOrganizerDecoder(dct):
    if '__date__' in dct:
        return datetime.date.fromordinal(dct["ordinal"])

    if '__episode__' in dct:
        return Episode(title = dct["title"], descriptor = dct["descriptor"], series = dct["series"], plot = dct['plot'], pictures = dct['pictures'], date = dct["date"], identifier = dct["identifier"], rating = dct["rating"], director = dct["director"], genre = dct["genre"], runtime = dct["runtime"], seen_it = dct["seen_it"], number = dct["number"])

    if '__series__' in dct:
        return Series(dct["title"], identifier = dct["identifier"], plot = dct["plot"], episodes = dct["episodes"], rating = dct["rating"], director = dct["director"], genre = dct["genre"], pictures = dct['pictures'], date = dct["date"])

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
            return { "__episode__" : True, "title" : obj.title, "descriptor" : obj.descriptor, "series" : obj.series, "plot" : obj.plot, "pictures" : obj.pictures, "date" : obj.date, "identifier" : obj.identifier, "rating" : obj.rating, "director" : obj.director, "runtime" : obj.runtime, "genre" : obj.genre, "seen_it" : obj.seen_it, "number" : obj.number}

        if isinstance(obj, datetime.date):
            return { "__date__" : True, "ordinal" : obj.toordinal()}

        if isinstance(obj, Series):
            return { "__series__" : True, "title" : obj.title, "plot" : obj.plot, "episodes" : obj.episodes, "identifier" : obj.identifier, "pictures" : obj.pictures,  "rating" : obj.rating,  "director" : obj.director, "genre" : obj.genre, "date" : obj.date}

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
                             "automatic_thumbnail_creation" : False,
                             "show_all_movieclips" : True,
                             "normalize_names" : True,
                             "hash_movieclips" : False,
                             "number_of_thumbnails" : 8,
                             "deployment_folder" : self.get_deployment_folder(),
                             "sources" : self.get_sources()
                             }
        else:
            self.settings = settings      


        self.valid_extensions = ("mkv", "avi", "mpgeg", "mpg", "wmv", "mp4", "mov")

    def __str__(self):
        return str(self.settings)
    
    def __getitem__(self, key):
        self.get(key)
        
    def __setitem__(self, key, value):
        self.settings[key] = value

    def get(self, attribute_name):
        try:
            return self.settings[attribute_name]
        except KeyError:
            pass

    def get_sources(self):
        dictionary = {"imdb" : {}, "tvrage" : {}} #TODO  
        return dict([[x, True] for x in dictionary.keys()])
    
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
            
    def get_deployment_folder(self):
        deployment_folder = os.path.join(self.get_user_dir(), "Series")
        if not os.path.exists(deployment_folder):
            os.makedirs(deployment_folder)        
        return deployment_folder
    
    def get_thumbnail_folder(self):        
        thumbnail_folder = os.path.join(self.get_settings_dir(), "thumbnails")
        if not os.path.exists(thumbnail_folder):
            os.makedirs(thumbnail_folder)        
        return thumbnail_folder
    
    def get_settings_dir(self, platform=sys.platform, appname="Diribeo"):        
        dirs = {"darwin": os.path.expandvars("$HOME/Library/Preferences"),
        "linux2": os.getenv("XDG_CONFIG_HOME", os.path.expandvars("$HOME/.config")),
        "win32": os.getenv("appdata")}
            
        setting_directory = os.path.join(dirs[platform].decode(sys.getfilesystemencoding()), appname)   
                
        if not os.path.exists(setting_directory):
            os.makedirs(setting_directory)                    
        return setting_directory

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
    
    
    def reset(self):
        self.__init__()
    
    def save_configs(self):
        self.save_movieclips()
        self.save_series()
        self.save_settings()
    
    
    def load_series(self):
        return self.load_file("series.json", [])    
        
    def load_movieclips(self):
        return self.load_file("movieclips.json", MovieClipManager())
    
    def save_series(self):
        self.save_file("series.json", series_list)
    
    def save_movieclips(self):
        self.save_file("movieclips.json", movieclips)
    
    def load_settings(self):
        return self.load_file("settings.json", Settings())
    
    def save_settings(self):
        self.save_file("settings.json", settings)
    
    
    def save_file(self, filename, contents):
        with open(os.path.join(self.get_settings_dir(), filename), "w") as f:
            f.write(json.dumps(contents, sort_keys = True, indent = 4, cls = SeriesOrganizerEncoder, encoding = "utf-8"))
        f.close()     
    
    def load_file(self, filename, default_value): 
        filepath = os.path.join(self.get_settings_dir(), filename)  
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                filecontents = f.read()
            f.close() 
            try:
                return json.loads(filecontents, object_hook = SeriesOrganizerDecoder, encoding = "utf-8")
            except ValueError: 
                return default_value
        
        return default_value 

class Series(object):
    def __init__(self, title, plot = None, identifier = None, episodes = None, rating = None, pictures = None, director = "", genre = "", date = ""):

        if episodes == None:
            episodes = []
            
        if identifier == None:
            identifier = {}
            
        if pictures == None:
            pictures = []

        self.episodes = episodes
        self.title = title
        self.rating = rating
        self.identifier = identifier
        self.director = director
        self.genre = genre
        self.date = date
        self.pictures = pictures
        self.plot = plot
        self.season = {}
    
    
    def __getitem__(self, key):
        ''' Returns the n-th episode of the series '''
        return self.episodes[key]

    def __len__(self):
        ''' Returns the number of episodes '''
        return len(self.episodes)

    def __repr__(self):
        return "S(" + self.title + " E: " + str(len(self.episodes)) + ")"


    def merge(self, new_series, merge_policy = MergePolicy.MORE_INFO):        
        if merge_policy == MergePolicy.MORE_INFO:
            pass
        elif merge_policy == MergePolicy.OVERWRITE:
            self.title = new_series.title
            self.rating = new_series.rating
            self.identifier = new_series.identifier
            self.director = new_series.director
            self.genre = new_series.genre
            self.date = new_series.date
        
        for index, new_episode in enumerate(new_series.episodes):
            try:
                self.episodes[index].merge(new_episode, merge_policy = merge_policy)
            except IndexError:
                self.episodes.append(new_episode)
    
    def get_seasons(self):
        ''' Returns a dictionary of seasons. Each season contains a list of episodes '''
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
        accumulated_movieclips =  [bucket for bucket in [episode.get_movieclips() for episode in self.episodes]]
        ouput_movieclips = []
        
        for bucket in accumulated_movieclips:
            for movieclip in bucket:
                ouput_movieclips.append(movieclip)
                
        return ouput_movieclips
        
    def get_identifier(self):
        return self.identifier.items()[0]
        
    def get_implementation_identifier(self):
        return self.identifier.items()[0][0]


    def get_episode_date_range(self):
        """ Returns the date of the first and last episode of this series
        """
        
        try:
            current_first_date = None
            current_last_date = None 
            
            
            for episode in self.episodes:
                if episode.date != None:                    
                    current_first_date = episode.date
                    break               
            
            for episode in reversed(self.episodes):
                if episode.date != None:
                    current_last_date = episode.date
                    break
            
            return current_first_date, current_last_date
        except IndexError:
            return datetime.date.today(), datetime.date.today()-datetime.timedelta(1)
        

class Episode(object):
    def __init__(self, title = "", descriptor = None, series = "", date = None, plot = "", identifier = None, rating = None, pictures = None, director = "", runtime = "", genre = "", seen_it = False, number = 0):
        
        if pictures == None:
            pictures = []
            
        self.title = title
        self.descriptor = descriptor
        self.series = series
        self.plot = plot
        self.date = date
        self.identifier = identifier
        self.rating = rating
        self.pictures = pictures
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
    
    def get_alternative_titles(self):
        return [self.series[0] + " " + "S" + str('%0.2d' % self.descriptor[0]) + "E" + str('%0.2d' % self.descriptor[1])]
    
    def get_identifier(self):
        # Use the first key as unique identifier. Note that this is propably not a good idea!
        return self.identifier.items()[0]
        
    def get_implementation_identifier(self):
        return self.identifier.items()[0][0]
    
    def merge(self, new_episode, merge_policy = MergePolicy.MORE_INFO):        
        # Don't overwrite series, identifier and the number, since the new episode might not have this info           
        if merge_policy == MergePolicy.MORE_INFO:
            if len(self.plot) < len(new_episode.plot):
                self.plot = new_episode.plot
            self.rating = new_episode.rating
        elif merge_policy == MergePolicy.OVERWRITE: 
            self.title = new_episode.title
            self.descriptor = new_episode.descriptor
            self.plot = new_episode.plot
            self.date = new_episode.date
            self.rating = new_episode.rating
            self.director = new_episode.director
            self.runtime = new_episode.runtime
            self.genre = new_episode.genre
            self.seen_it = new_episode.seen_it
            
    
    def get_ratings(self):
        return_text = ""
        for rating in self.rating:
            if self.rating[rating][0] != None:
                return_text = str(rating).upper() + ": " + str(self.rating[rating][0]) + " (" + str(self.rating[rating][1]) + ")\n" + return_text
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
            It returns two lists as a tuple. The first being a list of episodes. The second
            being a list of movie clips which match the checksum.
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
        ''' Checks if the given movie clip hasn't been assigned to a different episode
            Returns true if unique false otherwise
        '''
        
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


dummy_settings = Settings().load_settings()
settings = dummy_settings.load_settings()
series_list = dummy_settings.load_series()
movieclips = dummy_settings.load_movieclips()
