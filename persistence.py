import logging
import shelve

def persist_fields(**kwargs):
    def wrap_class(klass):
        #FIXME this will be a singleton for now
        filename = "{}.sav".format(klass.__name__)
        logging.debug("Opening shelf {}".format(filename))
        klass.db = shelve.open(filename, writeback=True)
        for attr_name, default_value in kwargs.items():
            def getter(self, attr_name=attr_name):
                logging.debug("Getting {}/{}".format(filename, attr_name))
                return klass.db[attr_name]
            def setter(self, value, attr_name=attr_name):
                logging.debug(
                        "Setting {}/{} to {}"
                        .format(filename, attr_name, value))
                klass.db[attr_name] = value
            if attr_name not in klass.db:
                logging.debug(
                    "Initializing {}/{} with default value {}"
                    .format(filename, attr_name, default_value))
                klass.db[attr_name] =  default_value
            logging.debug(
                    "Patching field {}.{} with {} and {}"
                    .format(klass, attr_name, getter, setter))
            setattr(klass, attr_name, property(getter, setter))
        return klass
    return wrap_class
    
