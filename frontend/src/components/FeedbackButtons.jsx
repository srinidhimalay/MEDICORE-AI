import React, { useState } from 'react';
import { submitFeedback } from '../services/api';

const FeedbackButtons = ({ chatId, messageIndex }) => {
  const [submitted, setSubmitted] = useState(null); // 'up', 'down', or null

  const handleFeedback = async (rating) => {
    const type = rating === 1 ? 'up' : 'down';
    if (submitted === type) return; // Already submitted this rating

    try {
      await submitFeedback(chatId, messageIndex, rating);
      setSubmitted(type);
    } catch (error) {
      console.error('Feedback submission failed:', error);
    }
  };

  return (
    <div
      className="feedback-buttons"
      style={{
        display: 'flex',
        gap: '4px',
        marginTop: '6px',
      }}
    >
      <button
        onClick={() => handleFeedback(1)}
        disabled={submitted !== null}
        aria-label="Thumbs up - helpful response"
        style={{
          background: 'none',
          border: 'none',
          cursor: submitted ? 'default' : 'pointer',
          fontSize: '0.9rem',
          opacity: submitted === 'down' ? 0.3 : 1,
          padding: '2px 6px',
          borderRadius: '4px',
          transition: 'background-color 0.2s',
        }}
        title="Helpful"
      >
        {submitted === 'up' ? '👍' : '👍🏻'}
      </button>
      <button
        onClick={() => handleFeedback(-1)}
        disabled={submitted !== null}
        aria-label="Thumbs down - not helpful response"
        style={{
          background: 'none',
          border: 'none',
          cursor: submitted ? 'default' : 'pointer',
          fontSize: '0.9rem',
          opacity: submitted === 'up' ? 0.3 : 1,
          padding: '2px 6px',
          borderRadius: '4px',
          transition: 'background-color 0.2s',
        }}
        title="Not helpful"
      >
        {submitted === 'down' ? '👎' : '👎🏻'}
      </button>
      {submitted && (
        <span style={{ fontSize: '0.7rem', color: '#888', alignSelf: 'center' }}>
          Thanks for your feedback
        </span>
      )}
    </div>
  );
};

export default FeedbackButtons;
