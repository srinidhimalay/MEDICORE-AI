import React, { useState } from "react";

const ChatInput = ({ onSend, disabled }) => {
  const [input, setInput] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (disabled) return;

    const trimmedInput = input.trim();
    if (trimmedInput) {
      onSend(trimmedInput);
      setInput("");
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter, but allow Shift+Enter for new line
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <form className="chat-input" onSubmit={handleSubmit}>
      <input
        type="text"
        placeholder="Describe your symptoms or reply..."
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        autoFocus
        aria-label="Type your medical question or describe your symptoms"
      />
    </form>
  );
};

export default ChatInput;
