import logging
import shelve

cache = {}

def shelve_open(filename):
    if filename not in cache:
        cache[filename] = shelve.open(filename, writeback=True)
    return cache[filename]

def persistent_attrs(**kwargs):
    def wrap_class(klass):
        for attr_name, default_value in kwargs.items():
            def getter(self, attr_name=attr_name, default_value=default_value):
                if attr_name not in self.db:
                    logging.debug(
                        "Initializing {}/{} with default value {}"
                        .format(self.db_filename, attr_name, default_value))
                    self.db[attr_name] = default_value
                return self.db[attr_name]
            def setter(self, value, attr_name=attr_name):
                logging.debug(
                    "Setting {}/{} to {}"
                    .format(self.db_filename, attr_name, value))
                self.db[attr_name] = value
            setattr(klass, attr_name, property(getter, setter))
        return klass
    return wrap_class

def persistent_attrs_init(self, id_str=None):
    if id_str is None:
        self.db_filename = "state/{}.sav".format(self.__class__.__name__)
    else:
        self.db_filename = "state/{}__{}.sav".format(self.__class__.__name__, id_str)
    logging.debug("Opening shelf {}".format(self.db_filename))
    self.db = shelve_open(self.db_filename)
