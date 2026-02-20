import React from 'react';

const CONFIDENCE_CONFIG = {
  high: { color: '#00cc00', label: 'High Confidence', icon: '●' },
  medium: { color: '#ffcc00', label: 'Moderate Confidence', icon: '●' },
  low: { color: '#ff6600', label: 'Low Confidence', icon: '●' },
};

const ConfidenceBadge = ({ confidence }) => {
  if (!confidence) return null;

  const config = CONFIDENCE_CONFIG[confidence] || CONFIDENCE_CONFIG.medium;

  return (
    <div
      className="confidence-badge"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '2px 8px',
        borderRadius: '12px',
        fontSize: '0.7rem',
        color: config.color,
        backgroundColor: `${config.color}15`,
        marginLeft: '8px',
      }}
      title={`Response confidence: ${config.label}`}
      aria-label={`Response confidence: ${config.label}`}
    >
      <span style={{ fontSize: '0.5rem' }}>{config.icon}</span>
      <span>{config.label}</span>
    </div>
  );
};

export default ConfidenceBadge;
