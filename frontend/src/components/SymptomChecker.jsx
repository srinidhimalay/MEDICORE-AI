import React, { useState } from "react";

const BODY_SYSTEMS = [
  {
    id: "head_neuro",
    label: "Head / Neuro",
    icon: "🧠",
    commonSymptoms: [
      "Headache", "Dizziness", "Memory issues", "Vision changes",
      "Facial pain / pressure", "Numbness or tingling", "Confusion",
      "Difficulty speaking", "Balance problems",
    ],
  },
  {
    id: "chest_heart",
    label: "Chest / Heart",
    icon: "❤️",
    commonSymptoms: [
      "Chest pain or tightness", "Palpitations", "Shortness of breath",
      "Persistent cough", "Wheezing", "Rapid heartbeat", "Swollen ankles",
    ],
  },
  {
    id: "abdomen",
    label: "Abdomen",
    icon: "🫃",
    commonSymptoms: [
      "Abdominal pain", "Nausea", "Vomiting", "Diarrhea", "Constipation",
      "Bloating", "Heartburn / acid reflux", "Blood in stool", "Loss of appetite",
    ],
  },
  {
    id: "skin",
    label: "Skin",
    icon: "🩹",
    commonSymptoms: [
      "Rash", "Itching", "Swelling", "Redness", "Blisters",
      "Skin discoloration", "Dry or scaly patches", "Hair loss",
    ],
  },
  {
    id: "limbs_joints",
    label: "Limbs / Joints",
    icon: "🦴",
    commonSymptoms: [
      "Joint pain", "Muscle pain / aches", "Swollen joint", "Stiffness",
      "Muscle weakness", "Leg cramps", "Back pain",
    ],
  },
  {
    id: "mental_health",
    label: "Mental Health",
    icon: "💭",
    commonSymptoms: [
      "Anxiety", "Low mood / depression", "Insomnia / sleep problems",
      "Mood swings", "Stress", "Panic attacks", "Difficulty concentrating",
    ],
  },
  {
    id: "other",
    label: "Other / General",
    icon: "🌡️",
    commonSymptoms: [
      "Fever", "Fatigue / tiredness", "Unintentional weight loss",
      "Night sweats", "Loss of appetite", "Frequent infections", "Swollen lymph nodes",
    ],
  },
];

const DURATION_OPTIONS = [
  { value: "a few hours", label: "A few hours" },
  { value: "1–2 days", label: "1–2 days" },
  { value: "3–7 days", label: "3–7 days" },
  { value: "1–2 weeks", label: "1–2 weeks" },
  { value: "several weeks", label: "Several weeks" },
  { value: "more than a month", label: "More than a month" },
];

const SEVERITY_LABELS = {
  1: "Minimal",
  2: "Very mild",
  3: "Mild",
  4: "Mild-moderate",
  5: "Moderate",
  6: "Moderate-severe",
  7: "Severe",
  8: "Very severe",
  9: "Extreme",
  10: "Unbearable",
};

/**
 * Structured symptom input form.
 *
 * Props:
 *   onSend  {Function} — called with (queryString: string) — same as handleSendMessage
 *   onClose {Function} — called when user dismisses the modal
 */
const SymptomChecker = ({ onSend, onClose }) => {
  const [selectedSystem, setSelectedSystem] = useState(null);
  const [checkedSymptoms, setCheckedSymptoms] = useState([]);
  const [customSymptom, setCustomSymptom] = useState("");
  const [severity, setSeverity] = useState(5);
  const [duration, setDuration] = useState("");
  const [notes, setNotes] = useState("");

  const handleSystemSelect = (systemId) => {
    setSelectedSystem(systemId);
    setCheckedSymptoms([]);
  };

  const toggleSymptom = (symptom) => {
    setCheckedSymptoms((prev) =>
      prev.includes(symptom)
        ? prev.filter((s) => s !== symptom)
        : [...prev, symptom]
    );
  };

  const allSymptoms = [
    ...checkedSymptoms,
    ...(customSymptom.trim() ? [customSymptom.trim()] : []),
  ];

  const buildQuery = () => {
    if (!selectedSystem || allSymptoms.length === 0) return "";

    const system = BODY_SYSTEMS.find((s) => s.id === selectedSystem);
    const systemLabel = system ? system.label.toLowerCase() : "body";

    let symptomList = "";
    if (allSymptoms.length === 1) {
      symptomList = allSymptoms[0].toLowerCase();
    } else if (allSymptoms.length === 2) {
      symptomList = `${allSymptoms[0].toLowerCase()} and ${allSymptoms[1].toLowerCase()}`;
    } else {
      const last = allSymptoms[allSymptoms.length - 1];
      symptomList =
        allSymptoms
          .slice(0, -1)
          .map((s) => s.toLowerCase())
          .join(", ") + `, and ${last.toLowerCase()}`;
    }

    let query = `I have ${symptomList} affecting my ${systemLabel} system`;
    query += `, with a severity of ${severity}/10 (${SEVERITY_LABELS[severity] || ""})`;
    if (duration) query += `, for ${duration}`;
    query += ".";
    if (notes.trim()) query += ` ${notes.trim()}`;

    return query;
  };

  const canSubmit = selectedSystem && allSymptoms.length > 0;

  const handleSubmit = () => {
    const query = buildQuery();
    if (!query) return;
    onSend(query);
    onClose();
  };

  const currentSystem = BODY_SYSTEMS.find((s) => s.id === selectedSystem);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-card symptom-checker-modal"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="modal-header">
          <h2>🩺 Symptom Checker</h2>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <p className="symptom-checker-subtitle">
          Fill in the form below and Medicore AI will analyse your symptoms using its medical knowledge base.
        </p>

        {/* Step 1: Body System */}
        <div className="symptom-section">
          <h3 className="symptom-step-label">Step 1 — Select body system</h3>
          <div className="body-system-grid">
            {BODY_SYSTEMS.map((sys) => (
              <button
                key={sys.id}
                type="button"
                className={`body-system-card ${selectedSystem === sys.id ? "selected" : ""}`}
                onClick={() => handleSystemSelect(sys.id)}
              >
                <span className="system-icon">{sys.icon}</span>
                <span className="system-label">{sys.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Step 2: Symptoms */}
        {currentSystem && (
          <div className="symptom-section">
            <h3 className="symptom-step-label">Step 2 — Select symptoms</h3>
            <div className="symptom-checkbox-grid">
              {currentSystem.commonSymptoms.map((symptom) => (
                <label key={symptom} className="symptom-checkbox-item">
                  <input
                    type="checkbox"
                    checked={checkedSymptoms.includes(symptom)}
                    onChange={() => toggleSymptom(symptom)}
                  />
                  <span>{symptom}</span>
                </label>
              ))}
            </div>
            <input
              type="text"
              className="symptom-custom-input"
              placeholder="Other symptom (type here)…"
              value={customSymptom}
              onChange={(e) => setCustomSymptom(e.target.value)}
              maxLength={100}
            />
          </div>
        )}

        {/* Step 3: Severity */}
        {currentSystem && (
          <div className="symptom-section">
            <h3 className="symptom-step-label">
              Step 3 — Severity:{" "}
              <span className="severity-value">
                {severity}/10 — {SEVERITY_LABELS[severity]}
              </span>
            </h3>
            <input
              type="range"
              min={1}
              max={10}
              value={severity}
              onChange={(e) => setSeverity(Number(e.target.value))}
              className="severity-slider"
            />
            <div className="severity-scale-labels">
              <span>1 Minimal</span>
              <span>5 Moderate</span>
              <span>10 Unbearable</span>
            </div>
          </div>
        )}

        {/* Step 4: Duration */}
        {currentSystem && (
          <div className="symptom-section">
            <h3 className="symptom-step-label">Step 4 — Duration</h3>
            <div className="duration-options">
              {DURATION_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`duration-chip ${duration === opt.value ? "selected" : ""}`}
                  onClick={() => setDuration(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 5: Notes */}
        {currentSystem && (
          <div className="symptom-section">
            <h3 className="symptom-step-label">
              Step 5 — Additional notes <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>(optional)</span>
            </h3>
            <textarea
              className="form-textarea"
              rows={2}
              placeholder="e.g. Worse in the morning, triggered by cold air, no known allergies…"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={300}
            />
          </div>
        )}

        {/* Preview */}
        {canSubmit && (
          <div className="symptom-preview">
            <p className="symptom-preview-label">Query preview:</p>
            <p className="symptom-preview-text">{buildQuery()}</p>
          </div>
        )}

        {/* Actions */}
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleSubmit}
            disabled={!canSubmit}
            title={!canSubmit ? "Please select a body system and at least one symptom" : ""}
          >
            🩺 Check Symptoms
          </button>
        </div>
      </div>
    </div>
  );
};

export default SymptomChecker;
