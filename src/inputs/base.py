from abc import ABC, abstractmethod
import arcade


class Command(ABC):
    @abstractmethod
    def execute(self, window) -> None:
        pass
