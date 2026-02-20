import React from 'react';

const TriageBadge = ({ triage }) => {
  if (!triage) return null;

  const { level, reason, color, label, icon } = triage;

  return (
    <div
      className="triage-badge"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '4px 12px',
        borderRadius: '16px',
        fontSize: '0.8rem',
        fontWeight: '600',
        backgroundColor: `${color}20`,
        color: color,
        border: `1px solid ${color}40`,
        marginBottom: '8px',
      }}
      title={reason}
      aria-label={`Triage level: ${label}. ${reason}`}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </div>
  );
};

export default TriageBadge;
