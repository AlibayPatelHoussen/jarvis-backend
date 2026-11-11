"""
interface/voice.py
==================
Interface vocale de Jarvis.

Deux composants :
- VoiceInput  : micro → texte (Speech-to-Text)
- VoiceOutput : texte → voix (Text-to-Speech)

Bibliothèques :
- pyttsx3          : TTS offline, gratuit, sans internet
- SpeechRecognition: STT via Google (internet requis)
                     ou Sphinx (offline, moins précis)

Installation :
    pip install pyttsx3 SpeechRecognition pyaudio
"""

import logging
import queue
import re
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class VoiceOutputError(Exception):
    """Erreur spécifique à la synthèse vocale."""
    pass


class VoiceInputError(Exception):
    """Erreur spécifique à la reconnaissance vocale."""
    pass


class VoiceOutput:
    """
    Synthèse vocale (Text-to-Speech).
    Jarvis parle à voix haute via pyttsx3 (offline).

    Usage :
        tts = VoiceOutput()
        tts.speak("Bonjour !")
    """

    def __init__(
        self,
        language: str = "fr",
        engine_factory: Optional[Callable] = None,
    ):
        """
        Args:
            language       : Langue pour la voix ("fr" ou "en")
            engine_factory : Fonction qui crée le moteur (défaut :
                             pyttsx3.init). Sert surtout aux tests.

        Pourquoi un thread dédié ?
        pyttsx3 n'est pas thread-safe : le moteur doit être créé et
        utilisé dans le MÊME thread (COM sous Windows), et deux
        runAndWait() simultanés lèvent "run loop already started".
        Un seul thread "parleur" lit une file d'attente : les réponses
        sont dites une par une, dans l'ordre.
        """
        self.language = language
        self._engine = None
        self._available = False
        self._engine_factory = engine_factory
        self._queue: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._worker, name="jarvis-tts", daemon=True
        )
        self._thread.start()
        # Attendre la fin de l'initialisation pour connaître is_available
        self._ready.wait(timeout=10)

    def _worker(self) -> None:
        """Thread unique qui possède le moteur et exécute la file."""
        try:
            self._init_engine()
        finally:
            self._ready.set()
        if not self._available:
            return

        while True:
            item = self._queue.get()
            try:
                if item is None:  # signal d'arrêt
                    return
                func, args = item
                try:
                    func(*args)
                except Exception as e:
                    logger.debug(f"[Voice] Erreur TTS : {e}")
            finally:
                self._queue.task_done()

    def _submit(self, func: Callable, *args) -> bool:
        """Ajoute une tâche à la file du thread parleur."""
        if not self._available or not self._thread.is_alive():
            return False
        self._queue.put((func, args))
        return True

    def _init_engine(self) -> None:
        """Initialise le moteur (appelé dans le thread parleur)."""
        try:
            if self._engine_factory is not None:
                self._engine = self._engine_factory()
            else:
                import pyttsx3
                self._engine = pyttsx3.init()

            # Chercher une voix française
            voices = self._engine.getProperty("voices") or []
            french_voice = None

            for voice in voices:
                name = voice.name.lower()
                if any(w in name for w in ["french", "français", "hortense", "julie"]):
                    french_voice = voice.id
                    break

            if french_voice:
                self._engine.setProperty("voice", french_voice)
            elif voices:
                # Prendre la 2ème voix si disponible (souvent féminine)
                idx = 1 if len(voices) > 1 else 0
                self._engine.setProperty("voice", voices[idx].id)

            # Paramètres de vitesse et volume
            self._engine.setProperty("rate", 165)
            self._engine.setProperty("volume", 0.9)

            self._available = True
            logger.info("[Voice] Synthèse vocale initialisée")

        except ImportError:
            logger.warning("[Voice] pyttsx3 non installé — pip install pyttsx3")
        except Exception as e:
            logger.warning(f"[Voice] Erreur init TTS : {e}")

    def _say(self, text: str) -> None:
        """Dit le texte (exécuté dans le thread parleur)."""
        self._engine.say(text)
        self._engine.runAndWait()

    def speak(self, text: str) -> None:
        """
        Fait parler Jarvis et attend la fin de la phrase.

        Args:
            text : Texte à dire
        """
        if self.speak_async(text):
            self._queue.join()

    def speak_async(self, text: str) -> bool:
        """
        Parle en arrière-plan sans bloquer l'interface.

        Returns:
            True si le texte a été mis en file d'attente.
        """
        clean = self._clean_for_speech(text)
        if not clean:
            return False
        return self._submit(self._say, clean)

    def set_rate(self, rate: int) -> None:
        """Change la vitesse (80-300, défaut 165)."""
        self._submit(self._engine_set, "rate", max(80, min(300, rate)))

    def set_volume(self, volume: float) -> None:
        """Change le volume (0.0-1.0)."""
        self._submit(self._engine_set, "volume", max(0.0, min(1.0, volume)))

    def _engine_set(self, name: str, value) -> None:
        self._engine.setProperty(name, value)

    def shutdown(self, timeout: float = 10.0) -> None:
        """
        Termine les phrases en cours puis arrête le thread parleur.
        À appeler en quittant, sinon la dernière réponse est coupée.
        """
        if self._thread.is_alive():
            self._queue.put(None)
            self._thread.join(timeout=timeout)

    def _clean_for_speech(self, text: str) -> str:
        """
        Nettoie le texte pour la synthèse vocale.
        Supprime le markdown et les caractères spéciaux.
        """
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        text = re.sub(r"`(.*?)`", r"\1", text)
        text = re.sub(r"#{1,6}\s", "", text)
        text = re.sub(r"https?://\S+", "lien web", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @property
    def is_available(self) -> bool:
        """True si pyttsx3 est installé et fonctionnel."""
        return self._available


class VoiceInput:
    """
    Reconnaissance vocale (Speech-to-Text).
    Écoute le micro et retourne le texte reconnu.

    Usage :
        stt = VoiceInput()
        text = stt.listen()
        print(text)
    """

    def __init__(self, language: str = "fr-FR"):
        """
        Args:
            language : Code langue pour la reconnaissance
                       "fr-FR" pour français, "en-US" pour anglais
        """
        self.language = language
        self._recognizer = None
        self._available = False
        self._init_recognizer()

    def _init_recognizer(self) -> None:
        """Initialise le recognizer."""
        try:
            import speech_recognition as sr
            self._sr = sr
            self._recognizer = sr.Recognizer()
            self._recognizer.pause_threshold = 1.0
            self._recognizer.dynamic_energy_threshold = True
            self._available = True
            logger.info("[Voice] Reconnaissance vocale initialisée")
        except ImportError:
            logger.warning(
                "[Voice] SpeechRecognition non installé\n"
                "        pip install SpeechRecognition pyaudio"
            )
        except Exception as e:
            logger.warning(f"[Voice] Erreur init STT : {e}")

    def listen(self, timeout: int = 10) -> Optional[str]:
        """
        Écoute le micro et retourne le texte reconnu.

        Args:
            timeout : Secondes d'attente avant abandon

        Returns:
            Texte reconnu ou None si échec
        """
        if not self._available:
            return None

        try:
            with self._sr.Microphone() as source:
                # Calibrer le bruit ambiant
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)

                audio = self._recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=15
                )

            # Reconnaissance via Google (internet requis)
            text = self._recognizer.recognize_google(
                audio,
                language=self.language
            )
            logger.info(f"[Voice] Reconnu : {text!r}")
            return text

        except self._sr.WaitTimeoutError:
            logger.debug("[Voice] Timeout — pas de son détecté")
            return None
        except self._sr.UnknownValueError:
            logger.debug("[Voice] Audio incompréhensible")
            return None
        except self._sr.RequestError as e:
            logger.warning(f"[Voice] Service Google indisponible : {e}")
            return None
        except Exception as e:
            logger.debug(f"[Voice] Erreur écoute : {e}")
            return None

    @property
    def is_available(self) -> bool:
        """True si SpeechRecognition et pyaudio sont installés."""
        return self._available
