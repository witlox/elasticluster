import logging
from schema import Optional, Schema

from elasticluster import log
from elasticluster.validate import nonempty_str, boolean, readable_file


class Login(object):
    rules = {'image_user': nonempty_str,
             'image_sudo': boolean,
             'user_key_name': str,  # FIXME: are there restrictions? (e.g., alphanumeric)
             'user_key_private': readable_file,
             Optional('user_key_public'): readable_file,
             Optional('image_user_sudo', default="root"): nonempty_str,
             Optional('image_userdata', default=''): str}

    def __init__(self, name, **kwargs):
        self.name = name
        self.options = Schema(self.rules).validate(kwargs)
        if log.very_verbose:
            log.debug('%s options: %s', self.name, dict(self.options))
