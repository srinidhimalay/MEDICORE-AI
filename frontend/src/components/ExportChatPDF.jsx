import { useState } from 'react';
import { jsPDF } from 'jspdf';

const ExportChatPDF = ({ messages, chatId }) => {
  const [exporting, setExporting] = useState(false);

  /**
   * Strip everything that jsPDF (Windows-1252 encoding) can't render cleanly:
   * emojis, smart quotes, unicode symbols, zero-width chars, etc.
   * Keeps only printable ASCII (0x20–0x7E) and newlines.
   */
  const sanitizeForPDF = (text) => {
    if (!text) return '';
    return text
      // common unicode replacements before stripping
      .replace(/[\u2018\u2019]/g, "'")   // smart single quotes
      .replace(/[\u201C\u201D]/g, '"')   // smart double quotes
      .replace(/\u2013/g, '-')           // en dash
      .replace(/\u2014/g, '--')          // em dash
      .replace(/\u2022/g, '-')           // bullet
      .replace(/\u2026/g, '...')         // ellipsis
      .replace(/\u00B7/g, '-')           // middle dot
      // strip everything else outside printable ASCII (keeps \n \r \t)
      .replace(/[^\x09\x0A\x0D\x20-\x7E]/g, '')
      // clean up markdown syntax
      .replace(/\*\*(.*?)\*\*/g, '$1')
      .replace(/\*(.*?)\*/g, '$1')
      .replace(/#{1,6}\s+/g, '')
      .replace(/`{1,3}([^`]*)`{1,3}/g, '$1')
      .replace(/---+/g, '')
      .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
      // normalise whitespace
      .replace(/[ \t]+/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  };

  const handleExport = () => {
    if (!messages || messages.length === 0) return;
    setExporting(true);

    try {
      const doc = new jsPDF({ unit: 'mm', format: 'a4' });
      const pageW = doc.internal.pageSize.getWidth();
      const pageH = doc.internal.pageSize.getHeight();
      const margin = 16;
      const contentW = pageW - margin * 2;
      let y = 20;

      const checkPage = (needed = 6) => {
        if (y + needed > pageH - 18) {
          doc.addPage();
          y = 20;
        }
      };

      // ── Header ───────────────────────────────────────────────────
      doc.setFontSize(17);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(30, 30, 30);
      doc.text('MediCore AI - Chat Export', margin, y);
      y += 7;

      doc.setFontSize(8);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(130, 130, 130);
      doc.text(`Exported: ${new Date().toLocaleString()}`, margin, y);
      y += 10;

      doc.setDrawColor(210, 210, 210);
      doc.line(margin, y, pageW - margin, y);
      y += 8;

      // ── Messages ─────────────────────────────────────────────────
      for (const msg of messages) {
        if (msg.isError) continue;

        const isUser = msg.role === 'user';
        const label = isUser ? 'You' : 'MediCore AI';

        // Build text content from formatted sections or raw content
        let rawText = '';
        if (!isUser && msg.formatted && msg.formatted.length > 0) {
          rawText = msg.formatted
            .map(s => `${s.header.replace(/\*\*/g, '')}\n${s.content.join('\n')}`)
            .join('\n\n');
        } else {
          rawText = msg.content || '';
        }

        const content = sanitizeForPDF(rawText);
        if (!content) continue;

        checkPage(14);

        // Role label pill
        const labelColor = isUser ? [0, 122, 204] : [34, 139, 34];
        doc.setFontSize(9);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(...labelColor);
        doc.text(label, margin, y);
        y += 5;

        // Message body — split by newlines first, then wrap each paragraph
        doc.setFontSize(9);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(40, 40, 40);

        const paragraphs = content.split(/\n+/);
        for (const para of paragraphs) {
          const trimmed = para.trim();
          if (!trimmed) {
            y += 2; // small gap for blank lines
            continue;
          }
          const lines = doc.splitTextToSize(trimmed, contentW);
          for (const line of lines) {
            checkPage(5);
            doc.text(line, margin, y);
            y += 4.5;
          }
          y += 1; // gap between paragraphs
        }

        y += 5; // gap between messages

        // Thin separator between messages
        checkPage(3);
        doc.setDrawColor(230, 230, 230);
        doc.line(margin, y, pageW - margin, y);
        y += 6;
      }

      // ── Footer ───────────────────────────────────────────────────
      checkPage(10);
      doc.setDrawColor(210, 210, 210);
      doc.line(margin, y, pageW - margin, y);
      y += 5;
      doc.setFontSize(7);
      doc.setFont('helvetica', 'italic');
      doc.setTextColor(160, 160, 160);
      doc.text(
        'This information is for educational purposes only and is not a substitute for professional medical advice.',
        margin,
        y
      );

      const filename = `medicore-chat-${chatId || 'export'}-${Date.now()}.pdf`;
      doc.save(filename);
    } catch (error) {
      console.error('PDF export failed:', error);
    } finally {
      setExporting(false);
    }
  };

  if (!messages || messages.length === 0) return null;

  return (
    <button
      onClick={handleExport}
      disabled={exporting}
      aria-label="Export chat as PDF"
      title="Export chat as PDF"
      style={{
        background: 'none',
        border: '1px solid #333',
        borderRadius: '8px',
        padding: '6px 10px',
        cursor: exporting ? 'default' : 'pointer',
        color: '#ccc',
        fontSize: '0.85rem',
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        opacity: exporting ? 0.6 : 1,
      }}
    >
      <span>{exporting ? '...' : 'PDF'}</span>
      <span>Export</span>
    </button>
  );
};

export default ExportChatPDF;