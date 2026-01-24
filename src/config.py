import os

import yaml


class F1RaceReplayConfig:
    def __init__(self):
        self.CONFIG_FILE_DIRECTORY = "src/config_files"
        self.LOGGING_CONFIG = self.load_config_file("logging_config.yaml")

    def load_config_file(self, file):
        config = ""
        filepath = os.path.join(self.CONFIG_FILE_DIRECTORY, file)
        try:
            with open(filepath, "r") as f:
                try:
                    config = yaml.safe_load(f)
                except yaml.YAMLError as e:
                    print(e)
                    return yaml.YAMLError
            return config
        except FileNotFoundError:
            raise FileNotFoundError
