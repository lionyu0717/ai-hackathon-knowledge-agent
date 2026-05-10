import { useCallback, useEffect, useState } from "react";
import { useDropzone } from "react-dropzone";

export type TextbookSummary = {
  textbook_id: string;
  filename: string;
  title: string;
  file_format: string;
  total_pages: number;
  total_chars: number;
  chapter_count: number;
  parse_status: "pending" | "parsing" | "done" | "failed";
  error_message: string | null;
  uploaded_at: string;
};

const STATUS_COLOR: Record<string, string> = {
  pending: "#888",
  parsing: "#d97706",
  done: "#16a34a",
  failed: "#dc2626",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "待解析",
  parsing: "解析中",
  done: "已完成",
  failed: "失败",
};

export function UploadPanel(props: {
  onSelect?: (textbook: TextbookSummary) => void;
  selectedId?: string | null;
}) {
  const [textbooks, setTextbooks] = useState<TextbookSummary[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/textbooks");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = (await r.json()) as TextbookSummary[];
      setTextbooks(data);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  // initial + 3s polling when any item is parsing
  useEffect(() => {
    refresh();
    const t = setInterval(() => {
      const hasParsing = textbooks.some((t) => t.parse_status === "parsing");
      if (hasParsing) refresh();
    }, 3000);
    return () => clearInterval(t);
  }, [refresh, textbooks]);

  const onDrop = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      setUploading(true);
      setError(null);
      try {
        const fd = new FormData();
        files.forEach((f) => fd.append("files", f));
        const r = await fetch("/api/upload", { method: "POST", body: fd });
        if (!r.ok) throw new Error(await r.text());
        await refresh();
      } catch (e) {
        setError(String(e));
      } finally {
        setUploading(false);
      }
    },
    [refresh]
  );

  const onDelete = useCallback(
    async (id: string) => {
      if (!confirm("删除这本教材？")) return;
      await fetch(`/api/textbooks/${id}`, { method: "DELETE" });
      await refresh();
    },
    [refresh]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "text/markdown": [".md", ".markdown"],
      "text/plain": [".txt"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    multiple: true,
  });

  return (
    <div style={{ padding: "1rem", borderRight: "1px solid #e5e7eb", height: "100%", overflowY: "auto" }}>
      <h3 style={{ marginTop: 0, marginBottom: "0.75rem" }}>📚 教材管理</h3>

      <div
        {...getRootProps()}
        style={{
          border: `2px dashed ${isDragActive ? "#2563eb" : "#cbd5e1"}`,
          borderRadius: 8,
          padding: "1.25rem 1rem",
          textAlign: "center",
          cursor: "pointer",
          background: isDragActive ? "#eff6ff" : "#f8fafc",
          transition: "all 0.15s",
        }}
      >
        <input {...getInputProps()} />
        <div style={{ fontSize: 32, lineHeight: 1, marginBottom: 6 }}>📥</div>
        {uploading ? (
          <div>上传中...</div>
        ) : isDragActive ? (
          <div>松开以上传</div>
        ) : (
          <div style={{ fontSize: 13 }}>
            拖拽文件到此处，或<u>点击选择</u>
            <div style={{ color: "#94a3b8", fontSize: 11, marginTop: 4 }}>
              支持 PDF / Markdown / TXT / DOCX
            </div>
          </div>
        )}
      </div>

      {error && (
        <div style={{ marginTop: 8, padding: 8, color: "#c33", fontSize: 12, background: "#fee2e2", borderRadius: 6 }}>
          {error}
        </div>
      )}

      <div style={{ marginTop: "1rem" }}>
        <div style={{ fontSize: 12, color: "#64748b", marginBottom: 6 }}>
          已上传 {textbooks.length} 本
        </div>

        {textbooks.length === 0 && (
          <div style={{ fontSize: 12, color: "#94a3b8", padding: "1rem 0", textAlign: "center" }}>
            尚无教材，先上传 PDF 试试
          </div>
        )}

        {textbooks.map((tb) => {
          const selected = props.selectedId === tb.textbook_id;
          return (
            <div
              key={tb.textbook_id}
              onClick={() => tb.parse_status === "done" && props.onSelect?.(tb)}
              style={{
                padding: "0.6rem 0.7rem",
                marginBottom: 6,
                borderRadius: 6,
                border: selected ? "2px solid #2563eb" : "1px solid #e5e7eb",
                background: selected ? "#eff6ff" : "#fff",
                cursor: tb.parse_status === "done" ? "pointer" : "default",
                fontSize: 13,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontWeight: 600, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {tb.title || tb.filename}
                </div>
                <span
                  style={{
                    fontSize: 10,
                    padding: "2px 6px",
                    borderRadius: 10,
                    background: STATUS_COLOR[tb.parse_status] + "22",
                    color: STATUS_COLOR[tb.parse_status],
                    marginLeft: 6,
                  }}
                >
                  {STATUS_LABEL[tb.parse_status]}
                </span>
              </div>
              <div style={{ color: "#94a3b8", fontSize: 11, marginTop: 4 }}>
                {tb.file_format.toUpperCase()} · {tb.total_pages > 0 ? `${tb.total_pages} 页 · ` : ""}
                {tb.chapter_count} 章 · {(tb.total_chars / 1000).toFixed(0)}K 字
              </div>
              {tb.error_message && (
                <div style={{ color: "#c33", fontSize: 11, marginTop: 4 }}>{tb.error_message}</div>
              )}
              <div style={{ marginTop: 6, display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onDelete(tb.textbook_id); }}
                  style={{
                    fontSize: 11, padding: "2px 8px", border: "1px solid #e5e7eb",
                    background: "#fff", borderRadius: 4, cursor: "pointer", color: "#64748b",
                  }}
                >
                  删除
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
