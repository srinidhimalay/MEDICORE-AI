import React, { useState, useEffect, useRef } from "react";
import ChatMessage from "./components/ChatMessage";
import ChatInput from "./components/ChatInput";
import LoadingSpinner from "./components/LoadingSpinner";
import LanguageSelector from "./components/LanguageSelector";
import VoiceControls from "./components/VoiceControls";
import AuthScreen from "./components/AuthScreen";
import Sidebar from "./components/Sidebar";
import HealthProfileForm from "./components/HealthProfileForm";
import ExportChatPDF from "./components/ExportChatPDF";
import SymptomChecker from "./components/SymptomChecker";
import LabUploadModal from "./components/LabUploadModal";
import {
  sendMessage,
  sendMessageStream,
  sendImageMessage,
  sendLabResults,
  simplifyConversation,
  translateText,
  detectLanguage,
  getChatHistory,
  getChatDetail,
  createNewChat,
  deleteChat as deleteC,
  logout as logoutApi,
} from "./services/api";
import "./styles/App.css";
import "./styles/AuthScreen.css";
import "./styles/Sidebar.css";

function App() {
  const [user, setUser] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [currentChatId, setCurrentChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [awaitingFollowup, setAwaitingFollowup] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showSimplifyFor, setShowSimplifyFor] = useState(null);
  const [simplifying, setSimplifying] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState("en");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [showHealthProfile, setShowHealthProfile] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [showSymptomChecker, setShowSymptomChecker] = useState(false);
  const [selectedLabFile, setSelectedLabFile] = useState(null);
  const [labFilePreview, setLabFilePreview] = useState(null);
  const [showLabModal, setShowLabModal] = useState(false);
  const chatEndRef = useRef(null);
  const imageInputRef = useRef(null);
  const labFileInputRef = useRef(null);

  useEffect(() => {
    const savedUser = localStorage.getItem("medicore_user");
    const token = localStorage.getItem("medicore_token");
    if (savedUser && token) {
      setUser(JSON.parse(savedUser));
    }
  }, []);

  useEffect(() => {
    if (user) {
      loadConversations();
    }
  }, [user]);

  useEffect(() => {
    if (currentChatId) {
      loadChatMessages(currentChatId);
    }
  }, [currentChatId]);

  const loadConversations = async () => {
    try {
      const chats = await getChatHistory();
      setConversations(
        chats.map((chat) => ({
          id: chat.chat_id,
          title: chat.title,
          timestamp: chat.created_at,
          messageCount: chat.message_count,
        }))
      );
    } catch (error) {
      console.error("Failed to load conversations:", error);
    }
  };

  const loadChatMessages = async (chatId) => {
    try {
      const chatDetail = await getChatDetail(chatId);
      setMessages(
        chatDetail.messages.map((msg, idx) => {
          const isImageMsg = msg.role === "user" && msg.content.startsWith("[Image uploaded]");
          return {
            ...msg,
            content: isImageMsg ? msg.content.replace("[Image uploaded] ", "") : msg.content,
            id: `${chatId}-${idx}`,
            formatted: msg.role === "assistant" ? formatMedicalResponse(msg.content) : null,
            hadImage: isImageMsg,
          };
        })
      );
    } catch (error) {
      console.error("Failed to load chat messages:", error);
      setMessages([]);
    }
  };

  const handleLogin = (userData) => {
    setUser(userData);
  };

  const handleLogout = async () => {
    try {
      await logoutApi();
    } catch (error) {
      console.error("Logout error:", error);
    }
    setUser(null);
    setConversations([]);
    setMessages([]);
    setCurrentChatId(null);
    setAwaitingFollowup(false);
  };

  const newConversation = async () => {
    try {
      const response = await createNewChat();
      setCurrentChatId(response.chat_id);
      setMessages([]);
      setAwaitingFollowup(false);
      await loadConversations();
    } catch (error) {
      console.error("Failed to create new chat:", error);
    }
  };

  const selectConversation = (chatId) => {
    setCurrentChatId(chatId);
    setAwaitingFollowup(false);
  };

  const handleDeleteChat = async (chatId) => {
    try {
      await deleteC(chatId);
      if (currentChatId === chatId) {
        setCurrentChatId(null);
        setMessages([]);
      }
      await loadConversations();
    } catch (error) {
      console.error("Failed to delete chat:", error);
    }
  };

  const formatMedicalResponse = (responseText) => {
    const sections = {
      // Old format (backwards compatible)
      "**Overview**": { icon: "📋" },
      "**Possible Causes**": { icon: "🔍" },
      "**Common Symptoms**": { icon: "⚠️" },
      "**Recommended Actions**": { icon: "✅" },
      "**When to Seek Medical Care**": { icon: "🏥" },
      "**Medical Disclaimer**": { icon: "⚖️" },
      // New adaptive format - Symptom queries
      "**Understanding Your Concern**": { icon: "💭" },
      "**What This Could Indicate**": { icon: "🔍" },
      "**Key Symptoms to Monitor**": { icon: "⚠️" },
      "**Recommended Steps**": { icon: "✅" },
      "**Seek Medical Attention If**": { icon: "🚨" },
      // New adaptive format - Condition queries
      "**Causes and Risk Factors**": { icon: "🔍" },
      "**Signs and Symptoms**": { icon: "⚠️" },
      "**Management and Treatment**": { icon: "💊" },
      "**Living With This Condition**": { icon: "🌱" },
      // New adaptive format - Medication queries
      "**Medication Overview**": { icon: "💊" },
      "**Common Uses**": { icon: "📋" },
      "**Important Safety Information**": { icon: "⚠️" },
      "**Usage Guidance**": { icon: "📝" },
    };

    let formatted = [];
    const lines = responseText.split("\n");
    let currentSection = null;
    let currentContent = [];

    lines.forEach((line) => {
      const lineTrimmed = line.trim();
      for (const [header, meta] of Object.entries(sections)) {
        if (lineTrimmed.includes(header)) {
          if (currentSection && currentContent.length > 0) {
            formatted.push({
              type: "section",
              header: currentSection.header,
              icon: currentSection.icon,
              content: currentContent.filter((c) => c.trim()),
            });
          }
          currentSection = { header, icon: meta.icon };
          currentContent = [];
          return;
        }
      }
      if (lineTrimmed && currentSection) {
        currentContent.push(lineTrimmed);
      }
    });

    if (currentSection && currentContent.length > 0) {
      formatted.push({
        type: "section",
        header: currentSection.header,
        icon: currentSection.icon,
        content: currentContent.filter((c) => c.trim()),
      });
    }

    return formatted.length > 0 ? formatted : null;
  };

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async (message) => {
    const originalMessage = message;
    let processedMessage = message;
    let detectedLang = "en";

    if (selectedLanguage !== "en") {
      try {
        const detectionResult = await detectLanguage(message);
        detectedLang = detectionResult.language;
      } catch (error) {
        console.warn("Language detection failed:", error);
      }
    }

    if (detectedLang !== "en") {
      try {
        const translationResult = await translateText(message, "en", detectedLang);
        processedMessage = translationResult.translated_text;
      } catch (error) {
        console.warn("Translation failed:", error);
      }
    }

    const newUserMessage = {
      role: "user",
      content: originalMessage,
      id: Date.now() + "-user",
    };

    const updatedMessages = [...messages, newUserMessage];
    setMessages(updatedMessages);
    setLoading(true);

    try {
      const assistantId = Date.now();
      let streamedContent = "";

      // Add a placeholder assistant message for streaming
      const placeholderMessage = {
        role: "assistant",
        content: "",
        id: assistantId,
        isFollowup: false,
        formatted: "",
        sources: null,
        confidence: null,
        triage: null,
        isStreaming: true,
      };
      setMessages([...updatedMessages, placeholderMessage]);

      const result = await sendMessageStream(
        processedMessage,
        currentChatId,
        awaitingFollowup,
        (chunk) => {
          streamedContent += chunk;
          setMessages((prev) => {
            const updated = [...prev];
            const lastIdx = updated.length - 1;
            if (updated[lastIdx]?.id === assistantId) {
              updated[lastIdx] = {
                ...updated[lastIdx],
                content: streamedContent,
                formatted: formatMedicalResponse(streamedContent),
              };
            }
            return updated;
          });
        }
      );

      // Translate the full response if needed
      let finalContent = streamedContent;
      if (selectedLanguage !== "en") {
        try {
          const translationResult = await translateText(streamedContent, selectedLanguage, "en");
          finalContent = translationResult.translated_text;
        } catch (error) {
          console.warn("Translation back failed:", error);
        }
      }

      // Finalize the assistant message with metadata
      setMessages((prev) => {
        const updated = [...prev];
        const lastIdx = updated.length - 1;
        if (updated[lastIdx]?.id === assistantId) {
          updated[lastIdx] = {
            ...updated[lastIdx],
            content: finalContent,
            formatted: formatMedicalResponse(finalContent),
            isFollowup: result.awaiting_followup,
            sources: result.sources || null,
            confidence: result.confidence || null,
            triage: result.triage || null,
            isStreaming: false,
          };
        }
        return updated;
      });

      setCurrentChatId(result.chat_id);
      setAwaitingFollowup(result.awaiting_followup);

      if (!result.awaiting_followup) {
        setShowSimplifyFor(assistantId);
      }

      await loadConversations();
    } catch (error) {
      console.error("Error sending message:", error);
      const errorMessage = {
        role: "assistant",
        content: "⚠️ Sorry, there was an error. Please try again.",
        id: Date.now(),
        isError: true,
      };
      setMessages([...updatedMessages, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleImageSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const validTypes = ["image/jpeg", "image/png", "image/webp"];
    if (!validTypes.includes(file.type)) {
      alert("Only JPEG, PNG, and WebP images are supported.");
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      alert("Image must be under 4MB.");
      return;
    }

    setSelectedImage(file);
    setImagePreview(URL.createObjectURL(file));
  };

  const clearImage = () => {
    setSelectedImage(null);
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setImagePreview(null);
    if (imageInputRef.current) imageInputRef.current.value = "";
  };

  const handleSendWithImage = async (message) => {
    if (!selectedImage) {
      handleSendMessage(message);
      return;
    }

    const file = selectedImage;
    clearImage();

    // Convert to data URL so it persists in chat history
    const imageDataUrl = await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.readAsDataURL(file);
    });

    const newUserMessage = {
      role: "user",
      content: message || "Analyze this image",
      id: Date.now() + "-user",
      imageUrl: imageDataUrl,
    };

    const updatedMessages = [...messages, newUserMessage];
    setMessages(updatedMessages);
    setLoading(true);

    try {
      const result = await sendImageMessage(file, message, currentChatId);

      const formatted = formatMedicalResponse(result.response);
      const assistantMessage = {
        role: "assistant",
        content: result.response,
        formatted,
        id: Date.now(),
      };

      setMessages([...updatedMessages, assistantMessage]);
      setCurrentChatId(result.chat_id);
      setAwaitingFollowup(false);
      await loadConversations();
    } catch (error) {
      console.error("Image analysis error:", error);
      const errorMessage = {
        role: "assistant",
        content: `⚠️ Image analysis failed: ${error.message}`,
        id: Date.now(),
        isError: true,
      };
      setMessages([...updatedMessages, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleSimplify = async (messageId) => {
    setSimplifying(true);
    try {
      const index = messages.findIndex((msg) => msg.id === messageId);
      const messagesToSimplify = index >= 0 ? messages.slice(0, index + 1) : messages;

      let textToSimplify = "";
      for (let i = messagesToSimplify.length - 1; i >= 0; i--) {
        if (messagesToSimplify[i].role === "assistant") {
          textToSimplify = messagesToSimplify[i].content;
          break;
        }
      }

      let processedText = textToSimplify;
      if (selectedLanguage !== "en") {
        try {
          const translationResult = await translateText(textToSimplify, "en", selectedLanguage);
          processedText = translationResult.translated_text;
        } catch (error) {
          console.warn("Translation failed:", error);
        }
      }

      const simplifiedHistory = [{ role: "assistant", content: processedText }];
      const response = await simplifyConversation(simplifiedHistory);
      let simplifiedText = response.simplified;

      if (selectedLanguage !== "en") {
        try {
          const translationResult = await translateText(simplifiedText, selectedLanguage, "en");
          simplifiedText = translationResult.translated_text;
        } catch (error) {
          console.warn("Translation back failed:", error);
        }
      }

      const simplifiedMessage = {
        role: "assistant",
        content: `🧩 **Simplified:**\n\n${simplifiedText}`,
        id: Date.now(),
        isSimplified: true,
      };

      setMessages([...messages, simplifiedMessage]);
      setShowSimplifyFor(null);
    } catch (error) {
      console.error("Simplification error:", error);
    } finally {
      setSimplifying(false);
    }
  };

  const handleExampleClick = (text) => {
    if (!loading) {
      handleSendMessage(text);
    }
  };

  const handleLabFileSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const validTypes = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
    if (!validTypes.includes(file.type)) {
      alert("Only JPEG, PNG, WebP images or PDF files are supported for lab results.");
      if (labFileInputRef.current) labFileInputRef.current.value = "";
      return;
    }
    const maxSize = file.type === "application/pdf" ? 10 * 1024 * 1024 : 4 * 1024 * 1024;
    if (file.size > maxSize) {
      alert(`File too large. Max ${file.type === "application/pdf" ? "10MB" : "4MB"}.`);
      if (labFileInputRef.current) labFileInputRef.current.value = "";
      return;
    }
    setSelectedLabFile(file);
    setLabFilePreview(file.name);
    setShowLabModal(true);
  };

  const handleSendLabResults = async (contextText) => {
    if (!selectedLabFile) return;
    const file = selectedLabFile;
    setSelectedLabFile(null);
    setLabFilePreview(null);
    setShowLabModal(false);
    if (labFileInputRef.current) labFileInputRef.current.value = "";
    setLoading(true);
    try {
      const result = await sendLabResults(file, contextText, currentChatId);
      setCurrentChatId(result.chat_id);
      const userMsg = {
        role: "user",
        content: contextText || "Lab results uploaded for interpretation",
        id: Date.now() - 1,
        isLabUpload: true,
        labFileName: file.name,
      };
      const assistantMsg = {
        role: "assistant",
        content: result.interpretation,
        id: Date.now(),
        isLabResult: true,
        labValues: result.lab_values || [],
        sources: result.sources,
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      await loadConversations();
    } catch (error) {
      console.error("Lab results error:", error);
      const errMsg = {
        role: "assistant",
        content: `Sorry, I couldn't process the lab report: ${error.message}`,
        id: Date.now(),
      };
      setMessages((prev) => [
        ...prev,
        { role: "user", content: contextText || "Lab report", id: Date.now() - 1 },
        errMsg,
      ]);
    } finally {
      setLoading(false);
    }
  };

  const getHospitalSearchTerm = (text) => {
    const lower = text.toLowerCase();
    // Map keywords to the specialist/department to search for
    const specialtyMap = [
      { keywords: ["skin", "rash", "dermat", "eczema", "acne", "psoriasis", "fungal", "dandruff", "scalp", "seborrheic"], specialty: "dermatologist" },
      { keywords: ["heart", "chest pain", "cardiac", "blood pressure", "hypertension", "cardiovascular"], specialty: "cardiologist" },
      { keywords: ["bone", "fracture", "joint", "orthop", "spine", "back pain", "arthritis", "knee", "shoulder"], specialty: "orthopedic hospital" },
      { keywords: ["eye", "vision", "ophthal", "cataract", "glaucoma"], specialty: "eye hospital" },
      { keywords: ["ear", "nose", "throat", "ent", "sinus", "tonsil", "hearing"], specialty: "ENT hospital" },
      { keywords: ["tooth", "dental", "gum", "oral"], specialty: "dental clinic" },
      { keywords: ["brain", "neuro", "headache", "migraine", "seizure", "nerve"], specialty: "neurologist" },
      { keywords: ["stomach", "digest", "gastro", "abdomen", "liver", "bowel", "nausea", "vomit"], specialty: "gastroenterologist" },
      { keywords: ["lung", "breath", "asthma", "pulmon", "cough", "respiratory", "bronch", "pneumon", "copd", "tuberculosis", "tb "], specialty: "pulmonologist" },
      { keywords: ["kidney", "urin", "bladder", "nephro", "renal"], specialty: "nephrologist" },
      { keywords: ["diabetes", "thyroid", "hormone", "endocrin", "insulin"], specialty: "endocrinologist" },
      { keywords: ["cancer", "tumor", "oncol", "malignant", "chemotherapy", "carcinoma"], specialty: "oncologist" },
      { keywords: ["child", "pediatr", "infant", "baby", "newborn"], specialty: "pediatrician" },
      { keywords: ["pregnan", "gynec", "obstet", "menstr", "ovary", "uterus", "pcos"], specialty: "gynecologist" },
      { keywords: ["mental", "depress", "anxiety", "psychiatr", "psychol", "bipolar", "schizo"], specialty: "psychiatrist" },
      { keywords: ["allerg", "immune", "autoimmune", "immunol"], specialty: "allergist" },
      { keywords: ["swollen", "swelling", "lymphaden", "neck lump"], specialty: "general surgeon" },
    ];

    // Count total keyword occurrences for each specialty instead of first-match
    let bestSpecialty = null;
    let bestCount = 0;

    for (const { keywords, specialty } of specialtyMap) {
      let count = 0;
      for (const kw of keywords) {
        // Count how many times this keyword appears in the text
        let idx = 0;
        while ((idx = lower.indexOf(kw, idx)) !== -1) {
          count++;
          idx += kw.length;
        }
      }
      if (count > bestCount) {
        bestCount = count;
        bestSpecialty = specialty;
      }
    }

    return bestSpecialty ? `${bestSpecialty} near me` : "hospital near me";
  };

  const handleFindHospitals = (query) => {
    if (!navigator.geolocation) {
      alert("Geolocation is not supported by your browser.");
      return;
    }

    const searchTerm = getHospitalSearchTerm(query);

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        const encodedSearch = encodeURIComponent(searchTerm);
        window.open(
          `https://www.google.com/maps/search/${encodedSearch}/@${latitude},${longitude},14z`,
          "_blank"
        );
      },
      (error) => {
        switch (error.code) {
          case error.PERMISSION_DENIED:
            alert("Location permission denied. Please enable location access in your browser settings to find nearby hospitals.");
            break;
          case error.POSITION_UNAVAILABLE:
            alert("Location information is unavailable. Please try again.");
            break;
          case error.TIMEOUT:
            alert("Location request timed out. Please try again.");
            break;
          default:
            alert("Unable to get your location. Please try again.");
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
    );
  };

  if (!user) {
    return <AuthScreen onLogin={handleLogin} />;
  }

  return (
    <div className="app-container">
      <Sidebar
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        conversations={conversations}
        currentConvId={currentChatId}
        onSelectConversation={selectConversation}
        onNewConversation={newConversation}
        onDeleteChat={handleDeleteChat}
        user={user}
        onLogout={handleLogout}
      />

      <main className="main-area">
        <header className="top-header">
          <button className="menu-btn" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label="Toggle sidebar">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="12" x2="21" y2="12"></line>
              <line x1="3" y1="6" x2="21" y2="6"></line>
              <line x1="3" y1="18" x2="21" y2="18"></line>
            </svg>
          </button>
          <div className="header-title">
            <span className="title-icon">🏥</span>
            <span>MEDICORE AI</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              className="profile-btn"
              onClick={() => setShowHealthProfile(true)}
              aria-label="Open health profile"
              title="Health Profile"
              style={{
                background: 'none',
                border: '1px solid #333',
                borderRadius: '8px',
                padding: '6px 10px',
                cursor: 'pointer',
                color: '#ccc',
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <span>👤</span>
              <span>Profile</span>
            </button>
            <ExportChatPDF messages={messages} chatId={currentChatId} />
            <LanguageSelector selectedLanguage={selectedLanguage} onLanguageChange={setSelectedLanguage} />
          </div>
        </header>

        <div className="chat-area">
          {messages.length === 0 ? (
            <div className="welcome-container">
              <div className="welcome-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                  <path d="M2 17l10 5 10-5"></path>
                  <path d="M2 12l10 5 10-5"></path>
                </svg>
              </div>
              <h1>How can I help you today?</h1>
              <p>Where medical expertise meets artificial intelligence — supporting better decisions, not replacing doctors.</p>

              <div className="feature-cards">
                <div className="feature-card" role="button" tabIndex={0} onClick={() => handleExampleClick("I have chest pain and shortness of breath")} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleExampleClick("I have chest pain and shortness of breath"); } }} aria-label="Example: Chest pain and shortness of breath">
                  <div className="card-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                      <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                  </div>
                  <div className="card-content">
                    <h3>Chest Pain</h3>
                    <p>I have chest pain and shortness of breath</p>
                  </div>
                </div>

                <div className="feature-card" role="button" tabIndex={0} onClick={() => handleExampleClick("I have a severe headache and nausea")} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleExampleClick("I have a severe headache and nausea"); } }} aria-label="Example: Severe headache and nausea">
                  <div className="card-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10"></circle>
                      <path d="M12 16v-4"></path>
                      <path d="M12 8h.01"></path>
                    </svg>
                  </div>
                  <div className="card-content">
                    <h3>Headache</h3>
                    <p>Severe headache with nausea symptoms</p>
                  </div>
                </div>

                <div className="feature-card" role="button" tabIndex={0} onClick={() => handleExampleClick("I have been coughing with fever for 3 days")} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleExampleClick("I have been coughing with fever for 3 days"); } }} aria-label="Example: Coughing with fever for 3 days">
                  <div className="card-icon">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
                    </svg>
                  </div>
                  <div className="card-content">
                    <h3>Fever & Cough</h3>
                    <p>Persistent cough with fever for 3 days</p>
                  </div>
                </div>
              </div>

              <div className="symptom-checker-trigger">
                <button
                  className="symptom-checker-open-btn"
                  onClick={() => setShowSymptomChecker(true)}
                  disabled={loading}
                >
                  🩺 Symptom Checker
                </button>
              </div>

            </div>
          ) : (
            <div className="messages-container">
              {messages.map((msg, index) => (
                <div key={msg.id || index} className={`msg-wrapper ${msg.role}`}>
                  <ChatMessage message={msg} formatted={msg.formatted} selectedLanguage={selectedLanguage} />

                  {/* Simplify button for all assistant messages */}
                  {msg.role === "assistant" && !msg.isFollowup && !msg.isError && !msg.isSimplified && !msg.isStreaming && (
                    <div className="message-actions" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <button className="simplify-action" onClick={() => handleSimplify(msg.id)} disabled={simplifying}>
                        {simplifying ? "⏳ Simplifying..." : "🧩 Simplify"}
                      </button>
                      <button className="simplify-action" onClick={() => {
                        const userQuery = messages.slice(0, index).reverse().find(m => m.role === "user")?.content || "";
                        handleFindHospitals(`${userQuery} ${msg.content}`);
                      }} aria-label="Find nearby hospitals">
                        🏥 Find Hospitals
                      </button>
                    </div>
                  )}

                </div>
              ))}
              {loading && <LoadingSpinner />}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>

        <div className="input-container">
          {imagePreview && (
            <div className="image-preview">
              <img src={imagePreview} alt="Upload preview" />
              <button className="image-preview-remove" onClick={clearImage} aria-label="Remove image">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>
          )}
          <div className="input-box">
            <button className="input-icon-btn" aria-label="Chat input" tabIndex={-1}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
            </button>
            <input
              type="file"
              ref={imageInputRef}
              accept="image/jpeg,image/png,image/webp"
              onChange={handleImageSelect}
              style={{ display: "none" }}
            />
            <input
              type="file"
              ref={labFileInputRef}
              accept="image/jpeg,image/png,image/webp,application/pdf"
              onChange={handleLabFileSelect}
              style={{ display: "none" }}
            />
            <button
              className="input-icon-btn image-upload-btn"
              onClick={() => imageInputRef.current?.click()}
              disabled={loading}
              aria-label="Upload image"
              title="Upload medical image"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <circle cx="8.5" cy="8.5" r="1.5"></circle>
                <polyline points="21 15 16 10 5 21"></polyline>
              </svg>
            </button>
            <button
              className="input-icon-btn lab-upload-btn"
              onClick={() => labFileInputRef.current?.click()}
              disabled={loading}
              aria-label="Upload lab results"
              title="Upload lab report (image or PDF)"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 3H15M9 3V14L4 20H20L15 14V3M9 3H15"></path>
                <circle cx="9" cy="17" r="1" fill="currentColor"></circle>
                <circle cx="14" cy="18.5" r="1" fill="currentColor"></circle>
              </svg>
            </button>
            <ChatInput onSend={selectedImage ? handleSendWithImage : handleSendMessage} disabled={loading} />
            <VoiceControls onSend={selectedImage ? handleSendWithImage : handleSendMessage} disabled={loading} selectedLanguage={selectedLanguage} />
            <button className="send-btn" onClick={() => { }} disabled={loading} aria-label="Send message">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
          <p className="disclaimer">MEDICORE can make mistakes. Consider checking important information.</p>
        </div>
      </main>

      {/* Health Profile Modal */}
      {showHealthProfile && (
        <HealthProfileForm onClose={() => setShowHealthProfile(false)} />
      )}

      {/* Symptom Checker Modal */}
      {showSymptomChecker && (
        <SymptomChecker
          onSend={(query) => {
            setShowSymptomChecker(false);
            handleSendMessage(query);
          }}
          onClose={() => setShowSymptomChecker(false)}
        />
      )}

      {/* Lab Upload Context Modal */}
      {showLabModal && (
        <LabUploadModal
          fileName={labFilePreview}
          onConfirm={handleSendLabResults}
          onCancel={() => {
            setShowLabModal(false);
            setSelectedLabFile(null);
            setLabFilePreview(null);
            if (labFileInputRef.current) labFileInputRef.current.value = "";
          }}
        />
      )}
    </div>
  );
}

export default App;