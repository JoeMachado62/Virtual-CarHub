"use client";

import { FormEvent, useState } from "react";

import { apiFetch } from "@/lib/api";

type ChatItem = {
  role: "user" | "assistant";
  message: string;
};

export function DannyChat({ accessToken }: { accessToken: string }) {
  const [message, setMessage] = useState("");
  const [items, setItems] = useState<ChatItem[]>([]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!message.trim()) return;

    const outgoing = message;
    setItems((prev) => [...prev, { role: "user", message: outgoing }]);
    setMessage("");

    const response = await apiFetch<{ reply: string; escalation_triggered: boolean }>(
      "/chat/message",
      {
        method: "POST",
        body: JSON.stringify({ message: outgoing })
      },
      accessToken
    );

    const reply = response.data?.reply || "Unable to respond right now.";
    setItems((prev) => [...prev, { role: "assistant", message: reply }]);
  }

  return (
    <div className="card">
      <h3>Danny Chat</h3>
      <div style={{ maxHeight: 240, overflowY: "auto", marginBottom: 12 }}>
        {items.map((item, idx) => (
          <p key={`${item.role}-${idx}`}>
            <strong>{item.role === "assistant" ? "Danny" : "You"}:</strong> {item.message}
          </p>
        ))}
      </div>
      <form onSubmit={onSubmit} style={{ display: "flex", gap: 8 }}>
        <input
          className="input"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="Ask about status, docs, recommendations, or returns"
        />
        <button className="button" type="submit">
          Send
        </button>
      </form>
    </div>
  );
}
