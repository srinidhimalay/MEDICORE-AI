import React, { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";

const ChatMessage = ({ message, formatted, selectedLanguage }) => {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);

  useEffect(() => {
    // Check if speech synthesis is supported
    if ("speechSynthesis" in window) {
      setSpeechSupported(true);
    }
  }, []);

  const speakText = (text) => {
    if (!speechSupported) {
      alert("❌ Text-to-speech is not supported in your browser.");
      return;
    }

    // Stop any ongoing speech
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);

    // Set language for speech synthesis
    const languageCodes = {
      en: "en-US",
      hi: "hi-IN",
      te: "te-IN",
      ta: "ta-IN",
      kn: "kn-IN",
      ml: "ml-IN",
    };

    utterance.lang = languageCodes[selectedLanguage] || "en-US";
    utterance.rate = 0.9; // Slightly slower for clarity
    utterance.pitch = 1;

    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    window.speechSynthesis.speak(utterance);
  };

  const stopSpeaking = () => {
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
  };

  const isUser = message.role === "user";

  // Extract plain text from message for TTS
  const getPlainText = (content) => {
    // Remove markdown formatting for speech
    return content
      .replace(/\*\*(.*?)\*\*/g, "$1") // Remove bold
      .replace(/\*(.*?)\*/g, "$1") // Remove italic
      .replace(/#{1,6}\s/g, "") // Remove headers
      .replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1") // Remove links, keep text
      .replace(/`([^`]+)`/g, "$1") // Remove code
      .replace(/\n+/g, " ") // Replace newlines with spaces
      .trim();
  };

  // If message has formatted sections (medical response)
  if (!isUser && formatted && formatted.length > 0) {
    const fullText = formatted
      .map(
        (section) =>
          `${section.header.replace(/\*\*/g, "")}: ${section.content.join(" ")}`
      )
      .join(". ");

    return (
      <div className="message assistant-message">
        <div className="message-text">
          {formatted.map((section, idx) => (
            <div key={idx} className="medical-response">
              <div className="response-section-heading">
                <span className="section-icon">{section.icon}</span>
                <span>{section.header.replace(/\*\*/g, "")}</span>
              </div>
              <div className="response-section-content">
                {section.content.map((line, i) => (
                  <ReactMarkdown key={i}>{line}</ReactMarkdown>
                ))}
              </div>
            </div>
          ))}
        </div>
        {speechSupported && (
          <div className="message-controls">
            <button
              className={`tts-btn ${isSpeaking ? "speaking" : ""}`}
              onClick={
                isSpeaking
                  ? stopSpeaking
                  : () => speakText(getPlainText(fullText))
              }
              title={isSpeaking ? "🔊 Stop speaking" : "🔊 Speak response"}
              aria-label={
                isSpeaking ? "Stop text-to-speech" : "Start text-to-speech"
              }
            >
              {isSpeaking ? "🔊" : "🔈"}
            </button>
          </div>
        )}
      </div>
    );
  }

  // Helper: render a lab result status badge
  const LabStatusBadge = ({ status }) => {
    const labels = {
      normal: "Normal",
      high: "High",
      low: "Low",
      critical_high: "Critical High",
      critical_low: "Critical Low",
    };
    return (
      <span className={`lab-status-badge lab-status-${status}`}>
        {labels[status] || status}
      </span>
    );
  };

  // Lab result message: show extracted table + AI interpretation
  if (!isUser && message.isLabResult) {
    return (
      <div className="message assistant-message">
        {message.labValues && message.labValues.length > 0 && (
          <div className="lab-results-table-container">
            <h4 className="lab-table-title">🧪 Extracted Lab Values</h4>
            <div className="lab-table-scroll">
              <table className="lab-results-table">
                <thead>
                  <tr>
                    <th>Test</th>
                    <th>Value</th>
                    <th>Unit</th>
                    <th>Normal Range</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {message.labValues.map((lv, i) => {
                    const lo = lv.normal_low;
                    const hi = lv.normal_high;
                    const range =
                      lo !== null && lo !== undefined && hi !== null && hi !== undefined
                        ? `${lo} – ${hi}`
                        : lo !== null && lo !== undefined
                        ? `≥ ${lo}`
                        : hi !== null && hi !== undefined
                        ? `≤ ${hi}`
                        : "N/A";
                    return (
                      <tr key={i} className={`lab-row lab-row-${lv.status}`}>
                        <td className="lab-test-name">{lv.test_name}</td>
                        <td className="lab-value">{lv.value}</td>
                        <td className="lab-unit">{lv.unit}</td>
                        <td className="lab-range">{range}</td>
                        <td><LabStatusBadge status={lv.status} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
        <div className="message-text lab-interpretation">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
        {speechSupported && (
          <div className="message-controls">
            <button
              className={`tts-btn ${isSpeaking ? "speaking" : ""}`}
              onClick={isSpeaking ? stopSpeaking : () => speakText(getPlainText(message.content))}
              title={isSpeaking ? "🔊 Stop speaking" : "🔊 Speak response"}
              aria-label={isSpeaking ? "Stop text-to-speech" : "Start text-to-speech"}
            >
              {isSpeaking ? "🔊" : "🔈"}
            </button>
          </div>
        )}
      </div>
    );
  }

  // Regular message (user or unformatted assistant)
  return (
    <div className={`message ${isUser ? "user-message" : "assistant-message"}`}>
      {isUser && message.isLabUpload && (
        <div className="chat-image-indicator">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 3H15M9 3V14L4 20H20L15 14V3M9 3H15"></path>
          </svg>
          <span>Lab report: {message.labFileName || "Uploaded"}</span>
        </div>
      )}
      {isUser && message.imageUrl && (
        <div className="chat-image">
          <img src={message.imageUrl} alt="Uploaded medical image" />
        </div>
      )}
      {isUser && !message.imageUrl && message.hadImage && (
        <div className="chat-image-indicator">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <polyline points="21 15 16 10 5 21"></polyline>
          </svg>
          <span>Image was attached</span>
        </div>
      )}
      <div className="message-text">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
      {!isUser && speechSupported && (
        <div className="message-controls">
          <button
            className={`tts-btn ${isSpeaking ? "speaking" : ""}`}
            onClick={
              isSpeaking
                ? stopSpeaking
                : () => speakText(getPlainText(message.content))
            }
            title={isSpeaking ? "🔊 Stop speaking" : "🔊 Speak response"}
            aria-label={
              isSpeaking ? "Stop text-to-speech" : "Start text-to-speech"
            }
          >
            {isSpeaking ? "🔊" : "🔈"}
          </button>
        </div>
      )}
    </div>
  );
};

export default ChatMessage;