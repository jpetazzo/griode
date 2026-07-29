import logging
import os
import yaml

cache = {}

def persistent_attrs(**kwargs):
    def wrap_class(klass):
        for attr_name, default_value in kwargs.items():
            def getter(self, attr_name=attr_name, default_value=default_value):
                key = "{}.{}.{}".format(
                    self.__class__.__name__,
                    self.persistence_id,
                    attr_name)
                if key not in cache:
                    file = os.path.join("state", key)
                    if os.path.isfile(file):
                        try:
                            with open(file) as f:
                                cache[key] = yaml.safe_load(f)
                        except:
                            logging.exception("Error while trying to load {}:".format(file))
                if key not in cache:
                    cache[key] = default_value
                return cache[key]
            def setter(self, value, attr_name=attr_name):
                key = "{}.{}.{}".format(
                    self.__class__.__name__,
                    self.persistence_id,
                    attr_name)
                logging.debug("Setting {} to {}".format(key, value))
                cache[key] = value
                file = os.path.join("state", key)
                with open(file, "w") as f:
                    try:
                        yaml.safe_dump(value, f)
                    except:
                        logging.exception("Error while trying to save {}:".format(file))
            setattr(klass, attr_name, property(getter, setter))
        return klass
    return wrap_class

def persistent_attrs_init(self, persistence_id=None):
    self.persistence_id = persistence_id
