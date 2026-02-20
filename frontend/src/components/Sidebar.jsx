import React from "react";
import "../styles/Sidebar.css";

function Sidebar({
  isOpen,
  onToggle,
  conversations,
  currentConvId,
  onSelectConversation,
  onNewConversation,
  onDeleteChat,
  user,
  onLogout,
}) {
  const handleDelete = (e, chatId) => {
    e.stopPropagation();
    if (window.confirm("Are you sure you want to delete this chat?")) {
      onDeleteChat(chatId);
    }
  };

  return (
    <>
      <button className="menu-toggle-btn" onClick={onToggle} aria-label="Toggle sidebar menu">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="3" y1="12" x2="21" y2="12"></line>
          <line x1="3" y1="6" x2="21" y2="6"></line>
          <line x1="3" y1="18" x2="21" y2="18"></line>
        </svg>
      </button>

      <div className={`sidebar ${isOpen ? "" : "closed"}`}>
        <div className="sidebar-header">
          <button className="new-chat-btn" onClick={onNewConversation}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            New chat
          </button>
        </div>

        <div className="conversations">
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`conversation-item ${currentConvId === conv.id ? "active" : ""}`}
              onClick={() => onSelectConversation(conv.id)}
              role="button"
              tabIndex={0}
              aria-label={`Open conversation: ${conv.title}`}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectConversation(conv.id); } }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
              <span className="conv-title">{conv.title}</span>
              <button
                className="delete-chat-btn"
                onClick={(e) => handleDelete(e, conv.id)}
                title="Delete chat"
                aria-label={`Delete conversation: ${conv.title}`}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </div>
          ))}
          {conversations.length === 0 && (
            <div className="no-conversations">
              <p>No conversations yet</p>
              <p className="hint">Click "New chat" to start</p>
            </div>
          )}
        </div>

        <div className="sidebar-footer">
          <div className="user-info">
            <div className="user-avatar">
              {user.name ? user.name.charAt(0).toUpperCase() : "👤"}
            </div>
            <div className="user-details">
              <span className="user-name">{user.name}</span>
              <span className="user-email">{user.email}</span>
            </div>
          </div>
          <button className="logout-btn" onClick={onLogout}>
            ← Log out
          </button>
        </div>
      </div>
    </>
  );
}

export default Sidebar;