import React, { useState } from "react";
import { signup, login } from "../services/api";
import "../styles/AuthScreen.css";

function AuthScreen({ onLogin }) {
  const [showAuth, setShowAuth] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const validateEmail = (email) => {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
  };

  const handleAuth = async (type) => {
    setError("");
    setLoading(true);

    // Validation
    if (!email || !password) {
      setError("Please fill in all fields");
      setLoading(false);
      return;
    }

    if (!validateEmail(email)) {
      setError("Please enter a valid email address");
      setLoading(false);
      return;
    }

    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      setLoading(false);
      return;
    }

    if (type === "register" && !name) {
      setError("Please enter your name");
      setLoading(false);
      return;
    }

    try {
      console.log(`🔐 Attempting ${type}...`);
      let data;

      if (type === "login") {
        data = await login(email, password);
        console.log("✅ Login successful:", data);
      } else if (type === "register") {
        data = await signup(email, password, name);
        console.log("✅ Signup successful:", data);
      }

      // Call onLogin with user data
      if (data && data.user) {
        console.log("✅ Calling onLogin with:", data.user);
        onLogin(data.user);
      } else {
        throw new Error("No user data received");
      }
    } catch (err) {
      console.error("❌ Auth error:", err);

      // Extract error message properly
      let errorMessage = "Authentication failed. Please try again.";

      if (err.message) {
        errorMessage = err.message;
      }

      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      {/* LEFT PANEL — decorative branding, hidden on mobile */}
      <div className="auth-panel-left" aria-hidden="true">
        <div className="auth-panel-orb auth-panel-orb--cyan" />
        <div className="auth-panel-orb auth-panel-orb--purple" />
        <div className="auth-panel-brand">
          <div className="auth-panel-icon">⚕</div>
          <h2 className="auth-panel-title">Medicore AI</h2>
          <p className="auth-panel-subtitle">
            Evidence-based medical insights,<br />
            powered by encyclopedic knowledge.
          </p>
          <ul className="auth-panel-features">
            <li>Symptom analysis &amp; differential guidance</li>
            <li>Lab result interpretation</li>
            <li>Multilingual medical Q&amp;A</li>
          </ul>
        </div>
      </div>

      {/* RIGHT PANEL — auth form */}
      <div className="auth-panel-right">
        <div className="auth-card">
          <div className="logo">
            <div className="logo-icon">⚕</div>
            <h1>MEDICORE AI</h1>
            <p>Your AI Medical Assistant</p>
          </div>

          {error && (
            <div className="error-message">
              ⚠️ {error}
            </div>
          )}

          {showAuth === "login" ? (
            <div>
              <div className="input-group">
                <label>Email</label>
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyPress={(e) => e.key === "Enter" && !loading && handleAuth("login")}
                  disabled={loading}
                  autoComplete="email"
                />
              </div>
              <div className="input-group">
                <label>Password</label>
                <input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyPress={(e) => e.key === "Enter" && !loading && handleAuth("login")}
                  disabled={loading}
                  autoComplete="current-password"
                />
              </div>
              <button
                className="btn"
                onClick={() => handleAuth("login")}
                disabled={loading}
              >
                {loading ? "Signing in..." : "Sign In"}
              </button>
              <div className="switch-auth">
                Don't have an account?{" "}
                <button
                  onClick={() => {
                    setShowAuth("register");
                    setError("");
                  }}
                  disabled={loading}
                >
                  Sign up
                </button>
              </div>
            </div>
          ) : (
            <div>
              <div className="input-group">
                <label>Name</label>
                <input
                  type="text"
                  placeholder="Your name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={loading}
                  autoComplete="name"
                />
              </div>
              <div className="input-group">
                <label>Email</label>
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                  autoComplete="email"
                />
              </div>
              <div className="input-group">
                <label>Password</label>
                <input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyPress={(e) => e.key === "Enter" && !loading && handleAuth("register")}
                  disabled={loading}
                  autoComplete="new-password"
                />
              </div>
              <button
                className="btn"
                onClick={() => handleAuth("register")}
                disabled={loading}
              >
                {loading ? "Creating Account..." : "Create Account"}
              </button>
              <div className="switch-auth">
                Already have an account?{" "}
                <button
                  onClick={() => {
                    setShowAuth("login");
                    setError("");
                  }}
                  disabled={loading}
                >
                  Sign in
                </button>
              </div>
            </div>
          )}

          <p className="disclaimer">
            For educational purposes only. Always consult a healthcare professional.
          </p>
        </div>
      </div>
    </div>
  );
}

export default AuthScreen;
