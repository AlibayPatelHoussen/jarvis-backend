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
import threading
from typing import Optional

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

    def __init__(self, language: str = "fr"):
        """
        Args:
            language : Langue pour la voix ("fr" ou "en")
        """
        self.language = language
        self._engine = None
        self._available = False
        self._lock = threading.Lock()
        self._init_engine()

    def _init_engine(self) -> None:
        """Initialise le moteur pyttsx3."""
        try:
            import pyttsx3
            self._engine = pyttsx3.init()

            # Chercher une voix française
            voices = self._engine.getProperty("voices")
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

    def speak(self, text: str) -> None:
        """
        Fait parler Jarvis.

        Args:
            text : Texte à dire
        """
        if not self._available or not self._engine:
            return

        clean = self._clean_for_speech(text)
        if not clean.strip():
            return

        try:
            with self._lock:
                self._engine.say(clean)
                self._engine.runAndWait()
        except Exception as e:
            logger.debug(f"[Voice] Erreur TTS : {e}")

    def speak_async(self, text: str) -> None:
        """Parle en arrière-plan sans bloquer l'interface."""
        t = threading.Thread(target=self.speak, args=(text,), daemon=True)
        t.start()

    def set_rate(self, rate: int) -> None:
        """Change la vitesse (80-300, défaut 165)."""
        if self._engine:
            self._engine.setProperty("rate", max(80, min(300, rate)))

    def set_volume(self, volume: float) -> None:
        """Change le volume (0.0-1.0)."""
        if self._engine:
            self._engine.setProperty("volume", max(0.0, min(1.0, volume)))

    def _clean_for_speech(self, text: str) -> str:
        """
        Nettoie le texte pour la synthèse vocale.
        Supprime le markdown et les caractères spéciaux.
        """
        import re
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
