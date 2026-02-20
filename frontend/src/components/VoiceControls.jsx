import React, { useState, useRef, useEffect } from "react";

const VoiceControls = ({ onSend, disabled, selectedLanguage }) => {
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const recognitionRef = useRef(null);
  const timeoutRef = useRef(null);

  /* =========================================
     INIT SPEECH RECOGNITION (ONCE)
     ========================================= */
  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsListening(true);
      setErrorMessage("");
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript.trim();

      if (transcript) {
        setIsProcessing(true);
        onSend(transcript);
      } else {
        setErrorMessage("No speech detected. Please try again.");
      }
    };

    recognition.onerror = (event) => {
      let message = "";

      switch (event.error) {
        case "not-allowed":
          message = "Microphone access denied.";
          break;
        case "no-speech":
          message = "No speech detected.";
          break;
        case "audio-capture":
          message = "No microphone found.";
          break;
        case "network":
          message = "Network error.";
          break;
        default:
          message = `Speech error: ${event.error}`;
      }

      setErrorMessage(message);
      setTimeout(() => setErrorMessage(""), 4000);
    };

    recognition.onend = () => {
      setIsListening(false);
      setIsProcessing(false);

      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.stop();
    };
  }, [onSend]);

  /* =========================================
     UPDATE LANGUAGE (SAFE)
     ========================================= */
  useEffect(() => {
    if (!recognitionRef.current) return;

    const languageCodes = {
      en: "en-US",
      hi: "hi-IN",
      te: "te-IN",
      ta: "ta-IN",
      kn: "kn-IN",
      ml: "ml-IN",
    };

    recognitionRef.current.lang =
      languageCodes[selectedLanguage] || "en-US";
  }, [selectedLanguage]);

  /* =========================================
     TOGGLE MIC
     ========================================= */
  const toggleListening = () => {
    if (disabled || isProcessing || !recognitionRef.current) return;

    if (isListening) {
      recognitionRef.current.stop();
      return;
    }

    try {
      recognitionRef.current.start();

      timeoutRef.current = setTimeout(() => {
        recognitionRef.current.stop();
        setErrorMessage("Recording timed out.");
      }, 30000);
    } catch (err) {
      console.error(err);
      setErrorMessage("Failed to start microphone.");
      setTimeout(() => setErrorMessage(""), 3000);
    }
  };

  return (
    <div className="voice-controls-container">
      <button
        type="button"
        className={`voice-mic-btn ${isListening ? "listening" : ""} ${isProcessing ? "processing" : ""
          }`}
        onClick={toggleListening}
        disabled={disabled || isProcessing}
        title={
          isProcessing
            ? "Processing..."
            : isListening
              ? "Stop listening"
              : "Tap to speak"
        }
        aria-label={
          isProcessing
            ? "Processing speech"
            : isListening
              ? "Stop listening"
              : "Start voice input"
        }
      >
        {isProcessing ? "⏳" : isListening ? "🔴" : "🎤"}
      </button>

      {errorMessage && (
        <div className="voice-error-message">{errorMessage}</div>
      )}
    </div>
  );
};

export default VoiceControls;
