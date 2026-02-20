import axios from "axios";

// IMPORTANT: Make sure this matches your backend URL.
// Normalize to avoid accidental double slashes like //api/chat/stream.
const RAW_API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_BASE_URL = RAW_API_BASE_URL.replace(/\/+$/, "");

console.log("🔧 API Base URL:", API_BASE_URL);

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 60000,
  // IMPORTANT: Set to false for local development
  withCredentials: false,
});

// Add auth token to requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("medicore_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    console.log("📤 Request:", config.method?.toUpperCase(), config.url);
    return config;
  },
  (error) => {
    console.error("❌ Request Error:", error);
    return Promise.reject(error);
  }
);

// Handle responses and errors
api.interceptors.response.use(
  (response) => {
    console.log("✅ Response:", response.status, response.config.url);
    return response;
  },
  (error) => {
    console.error("❌ Response Error:", {
      status: error.response?.status,
      message: error.message,
      data: error.response?.data,
    });

    if (error.response?.status === 401) {
      // Token expired or invalid
      console.log("🔒 Token expired, clearing auth data");
      localStorage.removeItem("medicore_token");
      localStorage.removeItem("medicore_user");
      // Reload page to show login screen
      window.location.reload();
    }

    return Promise.reject(error);
  }
);

// ==================== AUTH APIs ====================

export const signup = async (email, password, name) => {
  try {
    console.log("📝 Signup request:", { email, name });
    const response = await api.post("/api/auth/signup", {
      email,
      password,
      name,
    });

    console.log("✅ Signup response:", response.data);

    // Save token and user
    if (response.data.access_token) {
      localStorage.setItem("medicore_token", response.data.access_token);
      console.log("💾 Token saved");
    }

    if (response.data.user) {
      localStorage.setItem("medicore_user", JSON.stringify(response.data.user));
      console.log("💾 User saved:", response.data.user);
    }

    return response.data;
  } catch (error) {
    console.error("❌ Signup error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Signup failed";
    throw new Error(errorMessage);
  }
};

export const login = async (email, password) => {
  try {
    console.log("🔐 Login request:", { email });
    const response = await api.post("/api/auth/login", {
      email,
      password,
    });

    console.log("✅ Login response:", response.data);

    // Save token and user
    if (response.data.access_token) {
      localStorage.setItem("medicore_token", response.data.access_token);
      console.log("💾 Token saved");
    }

    if (response.data.user) {
      localStorage.setItem("medicore_user", JSON.stringify(response.data.user));
      console.log("💾 User saved:", response.data.user);
    }

    return response.data;
  } catch (error) {
    console.error("❌ Login error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Login failed";
    throw new Error(errorMessage);
  }
};

export const logout = async () => {
  try {
    console.log("👋 Logging out...");
    await api.post("/api/auth/logout");
  } catch (error) {
    console.error("⚠️ Logout error:", error);
  } finally {
    localStorage.removeItem("medicore_token");
    localStorage.removeItem("medicore_user");
    console.log("🗑️ Auth data cleared");
  }
};

// ==================== CHAT APIs ====================

export const createNewChat = async () => {
  try {
    console.log("💬 Creating new chat...");
    const response = await api.post("/api/chat/new");
    console.log("✅ Chat created:", response.data.chat_id);
    return response.data;
  } catch (error) {
    console.error("❌ Create chat error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Failed to create chat";
    throw new Error(errorMessage);
  }
};

export const getChatHistory = async () => {
  try {
    console.log("📜 Fetching chat history...");
    const response = await api.get("/api/chat/history");
    console.log("✅ Got", response.data.chats.length, "chats");
    return response.data.chats;
  } catch (error) {
    console.error("❌ Get history error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Failed to get chat history";
    throw new Error(errorMessage);
  }
};

export const getChatDetail = async (chatId) => {
  try {
    console.log("📖 Fetching chat detail:", chatId);
    const response = await api.get(`/api/chat/${chatId}`);
    console.log("✅ Got", response.data.messages.length, "messages");
    return response.data;
  } catch (error) {
    console.error("❌ Get chat detail error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Failed to get chat detail";
    throw new Error(errorMessage);
  }
};

export const deleteChat = async (chatId) => {
  try {
    console.log("🗑️ Deleting chat:", chatId);
    const response = await api.delete(`/api/chat/${chatId}`);
    console.log("✅ Chat deleted");
    return response.data;
  } catch (error) {
    console.error("❌ Delete chat error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Failed to delete chat";
    throw new Error(errorMessage);
  }
};

export const sendMessage = async (message, chatId = null, awaitingFollowup = false) => {
  try {
    console.log("💬 Sending message:", {
      message: message.substring(0, 50) + "...",
      chatId,
      awaitingFollowup,
    });

    const response = await api.post("/api/chat", {
      message,
      chat_id: chatId,
      awaiting_followup: awaitingFollowup,
    });

    console.log("✅ Got response:", {
      chatId: response.data.chat_id,
      awaitingFollowup: response.data.awaiting_followup,
    });

    return response.data;
  } catch (error) {
    console.error("❌ Send message error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Failed to send message";
    throw new Error(errorMessage);
  }
};

export const sendMessageStream = async (message, chatId = null, awaitingFollowup = false, onChunk) => {
  const token = localStorage.getItem("medicore_token");
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      message,
      chat_id: chatId,
      awaiting_followup: awaitingFollowup,
    }),
  });

  if (!response.ok) {
    throw new Error(`Stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = { chat_id: null, awaiting_followup: false, sources: null, triage: null, confidence: null };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === "chat_id") {
            result.chat_id = data.chat_id;
          } else if (data.type === "content") {
            onChunk(data.content);
          } else if (data.type === "triage") {
            result.triage = data.triage;
            result.confidence = data.confidence;
          } else if (data.type === "done") {
            result.awaiting_followup = data.awaiting_followup;
            result.sources = data.sources || null;
          } else if (data.type === "error") {
            throw new Error(data.message);
          }
        } catch (e) {
          if (e.message !== "error") console.warn("SSE parse error:", e);
        }
      }
    }
  }

  return result;
};

export const sendImageMessage = async (file, message, chatId = null) => {
  try {
    const formData = new FormData();
    formData.append("image", file);
    formData.append("message", message || "Please analyze this medical image.");
    if (chatId) formData.append("chat_id", chatId);

    const token = localStorage.getItem("medicore_token");
    const response = await axios.post(`${API_BASE_URL}/api/chat/image`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      timeout: 120000,
    });

    return response.data;
  } catch (error) {
    const errorMessage = error.response?.data?.detail || error.message || "Image analysis failed";
    throw new Error(errorMessage);
  }
};

export const sendLabResults = async (file, context = "", chatId = null) => {
  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("context", context || "");
    if (chatId) formData.append("chat_id", chatId);

    const token = localStorage.getItem("medicore_token");
    const response = await axios.post(`${API_BASE_URL}/api/chat/lab-results`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      timeout: 120000,
    });

    return response.data;
  } catch (error) {
    const errorMessage = error.response?.data?.detail || error.message || "Lab result interpretation failed";
    throw new Error(errorMessage);
  }
};

export const simplifyConversation = async (chatHistory) => {
  try {
    console.log("🧩 Simplifying...");
    const response = await api.post("/api/simplify", {
      chat_history: chatHistory,
    });
    console.log("✅ Simplified");
    return response.data;
  } catch (error) {
    console.error("❌ Simplify error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Simplification failed";
    throw new Error(errorMessage);
  }
};

export const translateText = async (text, targetLanguage, sourceLanguage = "auto") => {
  try {
    console.log("🌍 Translating to", targetLanguage);
    const response = await api.post("/api/translate", {
      text,
      target_language: targetLanguage,
      source_language: sourceLanguage,
    });
    console.log("✅ Translated");
    return response.data;
  } catch (error) {
    console.error("❌ Translate error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Translation failed";
    throw new Error(errorMessage);
  }
};

export const detectLanguage = async (text) => {
  try {
    console.log("🔍 Detecting language...");
    const response = await api.post("/api/detect-language", {
      text,
    });
    console.log("✅ Detected:", response.data.language);
    return response.data;
  } catch (error) {
    console.error("❌ Detect language error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Language detection failed";
    throw new Error(errorMessage);
  }
};

// ==================== HEALTH PROFILE APIs ====================

export const getHealthProfile = async () => {
  try {
    const response = await api.get("/api/profile");
    return response.data;
  } catch (error) {
    console.error("❌ Get profile error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Failed to get profile";
    throw new Error(errorMessage);
  }
};

export const updateHealthProfile = async (profileData) => {
  try {
    const response = await api.post("/api/profile", profileData);
    return response.data;
  } catch (error) {
    console.error("❌ Update profile error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Failed to update profile";
    throw new Error(errorMessage);
  }
};

export const deleteHealthProfile = async () => {
  try {
    const response = await api.delete("/api/profile");
    return response.data;
  } catch (error) {
    console.error("❌ Delete profile error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Failed to delete profile";
    throw new Error(errorMessage);
  }
};

// ==================== FEEDBACK API ====================

export const submitFeedback = async (chatId, messageIndex, rating, comment = null) => {
  try {
    const response = await api.post("/api/feedback", {
      chat_id: chatId,
      message_index: messageIndex,
      rating,
      comment,
    });
    return response.data;
  } catch (error) {
    console.error("❌ Feedback error:", error);
    const errorMessage = error.response?.data?.detail || error.message || "Failed to submit feedback";
    throw new Error(errorMessage);
  }
};

// ==================== HEALTH CHECK ====================

export const healthCheck = async () => {
  try {
    const response = await api.get("/health");
    return response.data;
  } catch (error) {
    console.error("❌ Health check failed:", error);
    throw error;
  }
};

export default api;
