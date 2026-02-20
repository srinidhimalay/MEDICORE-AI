import React, { useState, useEffect } from 'react';
import { getHealthProfile, updateHealthProfile, deleteHealthProfile } from '../services/api';

const HealthProfileForm = ({ onClose }) => {
  const [profile, setProfile] = useState({
    age: '',
    sex: '',
    height_cm: '',
    weight_kg: '',
    blood_type: '',
    known_conditions: '',
    current_medications: '',
    allergies: '',
    family_history: '',
    smoking: '',
    alcohol: '',
    exercise: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    try {
      setLoading(true);
      const data = await getHealthProfile();
      setProfile({
        age: data.age || '',
        sex: data.sex || '',
        height_cm: data.height_cm || '',
        weight_kg: data.weight_kg || '',
        blood_type: data.blood_type || '',
        known_conditions: (data.known_conditions || []).join(', '),
        current_medications: (data.current_medications || []).join(', '),
        allergies: (data.allergies || []).join(', '),
        family_history: (data.family_history || []).join(', '),
        smoking: data.smoking || '',
        alcohol: data.alcohol || '',
        exercise: data.exercise || '',
      });
    } catch (error) {
      console.error('Failed to load profile:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setMessage('');

      const profileData = {
        age: profile.age ? parseInt(profile.age) : null,
        sex: profile.sex || null,
        height_cm: profile.height_cm ? parseFloat(profile.height_cm) : null,
        weight_kg: profile.weight_kg ? parseFloat(profile.weight_kg) : null,
        blood_type: profile.blood_type || null,
        known_conditions: profile.known_conditions ? profile.known_conditions.split(',').map(s => s.trim()).filter(Boolean) : [],
        current_medications: profile.current_medications ? profile.current_medications.split(',').map(s => s.trim()).filter(Boolean) : [],
        allergies: profile.allergies ? profile.allergies.split(',').map(s => s.trim()).filter(Boolean) : [],
        family_history: profile.family_history ? profile.family_history.split(',').map(s => s.trim()).filter(Boolean) : [],
        smoking: profile.smoking || null,
        alcohol: profile.alcohol || null,
        exercise: profile.exercise || null,
      };

      await updateHealthProfile(profileData);
      setMessage('Profile saved successfully!');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      setMessage('Failed to save profile. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to delete your health profile?')) return;
    try {
      await deleteHealthProfile();
      setProfile({
        age: '', sex: '', height_cm: '', weight_kg: '', blood_type: '',
        known_conditions: '', current_medications: '', allergies: '',
        family_history: '', smoking: '', alcohol: '', exercise: '',
      });
      setMessage('Profile deleted.');
      setTimeout(() => setMessage(''), 3000);
    } catch (error) {
      setMessage('Failed to delete profile.');
    }
  };

  const handleChange = (field, value) => {
    setProfile(prev => ({ ...prev, [field]: value }));
  };

  if (loading) {
    return (
      <div className="health-profile-overlay">
        <div className="health-profile-form">
          <p>Loading profile...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="health-profile-overlay" onClick={(e) => {
      if (e.target === e.currentTarget) onClose();
    }}>
      <div className="health-profile-form">
        <div className="profile-header">
          <h2>Health Profile</h2>
          <button onClick={onClose} className="close-btn" aria-label="Close health profile form">&times;</button>
        </div>
        <p className="profile-subtitle">
          Your health information helps personalize medical responses. This data is stored securely and only used to improve your experience.
        </p>

        <div className="profile-grid">
          <div className="profile-field">
            <label>Age</label>
            <input
              type="number"
              value={profile.age}
              onChange={(e) => handleChange('age', e.target.value)}
              placeholder="e.g., 30"
              min="0"
              max="150"
            />
          </div>

          <div className="profile-field">
            <label>Sex</label>
            <select value={profile.sex} onChange={(e) => handleChange('sex', e.target.value)}>
              <option value="">Select...</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div className="profile-field">
            <label>Height (cm)</label>
            <input
              type="number"
              value={profile.height_cm}
              onChange={(e) => handleChange('height_cm', e.target.value)}
              placeholder="e.g., 170"
            />
          </div>

          <div className="profile-field">
            <label>Weight (kg)</label>
            <input
              type="number"
              value={profile.weight_kg}
              onChange={(e) => handleChange('weight_kg', e.target.value)}
              placeholder="e.g., 70"
            />
          </div>

          <div className="profile-field">
            <label>Blood Type</label>
            <select value={profile.blood_type} onChange={(e) => handleChange('blood_type', e.target.value)}>
              <option value="">Select...</option>
              <option value="A+">A+</option>
              <option value="A-">A-</option>
              <option value="B+">B+</option>
              <option value="B-">B-</option>
              <option value="AB+">AB+</option>
              <option value="AB-">AB-</option>
              <option value="O+">O+</option>
              <option value="O-">O-</option>
            </select>
          </div>

          <div className="profile-field">
            <label>Smoking</label>
            <select value={profile.smoking} onChange={(e) => handleChange('smoking', e.target.value)}>
              <option value="">Select...</option>
              <option value="never">Never</option>
              <option value="former">Former</option>
              <option value="current">Current</option>
            </select>
          </div>

          <div className="profile-field">
            <label>Alcohol</label>
            <select value={profile.alcohol} onChange={(e) => handleChange('alcohol', e.target.value)}>
              <option value="">Select...</option>
              <option value="none">None</option>
              <option value="moderate">Moderate</option>
              <option value="heavy">Heavy</option>
            </select>
          </div>

          <div className="profile-field">
            <label>Exercise</label>
            <select value={profile.exercise} onChange={(e) => handleChange('exercise', e.target.value)}>
              <option value="">Select...</option>
              <option value="sedentary">Sedentary</option>
              <option value="moderate">Moderate</option>
              <option value="active">Active</option>
            </select>
          </div>
        </div>

        <div className="profile-field full-width">
          <label>Known Conditions (comma-separated)</label>
          <input
            type="text"
            value={profile.known_conditions}
            onChange={(e) => handleChange('known_conditions', e.target.value)}
            placeholder="e.g., diabetes type 2, hypertension"
          />
        </div>

        <div className="profile-field full-width">
          <label>Current Medications (comma-separated)</label>
          <input
            type="text"
            value={profile.current_medications}
            onChange={(e) => handleChange('current_medications', e.target.value)}
            placeholder="e.g., metformin 500mg, lisinopril 10mg"
          />
        </div>

        <div className="profile-field full-width">
          <label>Allergies (comma-separated)</label>
          <input
            type="text"
            value={profile.allergies}
            onChange={(e) => handleChange('allergies', e.target.value)}
            placeholder="e.g., penicillin, sulfa drugs, peanuts"
          />
        </div>

        <div className="profile-field full-width">
          <label>Family History (comma-separated)</label>
          <input
            type="text"
            value={profile.family_history}
            onChange={(e) => handleChange('family_history', e.target.value)}
            placeholder="e.g., heart disease, diabetes, cancer"
          />
        </div>

        {message && (
          <div className={`profile-message ${message.includes('Failed') ? 'error' : 'success'}`}>
            {message}
          </div>
        )}

        <div className="profile-actions">
          <button onClick={handleSave} disabled={saving} className="save-btn">
            {saving ? 'Saving...' : 'Save Profile'}
          </button>
          <button onClick={handleDelete} className="delete-btn">
            Delete Profile
          </button>
        </div>
      </div>
    </div>
  );
};

export default HealthProfileForm;
