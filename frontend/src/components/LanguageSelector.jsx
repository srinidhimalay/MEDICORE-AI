import React from "react";

const LanguageSelector = ({ selectedLanguage, onLanguageChange }) => {
  // ONLY 6 LANGUAGES as requested: English, Hindi, Telugu, Tamil, Kannada, Malayalam
  const languages = [
    { code: "en", name: "English", nativeName: "English", flag: "🇬🇧" },
    { code: "hi", name: "Hindi", nativeName: "हिंदी", flag: "🇮🇳" },
    { code: "te", name: "Telugu", nativeName: "తెలుగు", flag: "🇮🇳" },
    { code: "ta", name: "Tamil", nativeName: "தமிழ்", flag: "🇮🇳" },
    { code: "kn", name: "Kannada", nativeName: "ಕನ್ನಡ", flag: "🇮🇳" },
    { code: "ml", name: "Malayalam", nativeName: "മലയാളം", flag: "🇮🇳" },
  ];

  return (
    <div className="language-selector">
      <span className="language-label">🌐</span>
      <select
        className="language-dropdown"
        value={selectedLanguage}
        onChange={(e) => onLanguageChange(e.target.value)}
        aria-label="Select language"
        title="Select your language for both text and voice"
      >
        {languages.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.flag} {lang.nativeName}
          </option>
        ))}
      </select>
    </div>
  );
};

export default LanguageSelector;