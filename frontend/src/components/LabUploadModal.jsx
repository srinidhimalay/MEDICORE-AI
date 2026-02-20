import React, { useState } from "react";

/**
 * Modal shown after user selects a lab report file.
 * Lets the user optionally add context text before sending.
 *
 * Props:
 *   fileName  {string}   — display name of the selected file
 *   onConfirm {Function} — called with contextText when user clicks "Interpret"
 *   onCancel  {Function} — called when user clicks Cancel
 */
const LabUploadModal = ({ fileName, onConfirm, onCancel }) => {
  const [contextText, setContextText] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    onConfirm(contextText.trim());
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div
        className="modal-card lab-upload-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>Interpret Lab Report</h2>
          <button className="modal-close-btn" onClick={onCancel} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="lab-upload-file-info">
          <span className="lab-file-icon">🧪</span>
          <span className="lab-file-name">{fileName}</span>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="lab-context">
              Additional context <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(optional)</span>
            </label>
            <textarea
              id="lab-context"
              className="form-textarea"
              rows={3}
              placeholder="e.g. Patient age 35, male, known diabetic. Fasting sample."
              value={contextText}
              onChange={(e) => setContextText(e.target.value)}
              maxLength={500}
            />
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textAlign: "right" }}>
              {contextText.length}/500
            </div>
          </div>

          <p className="lab-upload-note">
            The AI will extract lab values, compare against normal ranges, and provide a clinical interpretation.
          </p>

          <div className="modal-actions">
            <button type="button" className="btn-secondary" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="btn-primary">
              🔬 Interpret Results
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default LabUploadModal;
