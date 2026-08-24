"use client";

import React, { useState, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Conversation } from "@/components/chat/Conversation";
import { Composer } from "@/components/chat/Composer";
import { ContextPanel, type ContextTab } from "@/components/context/ContextPanel";
import { DEMO_PRINCIPALS } from "@/lib/constants";
import { apiUrl } from "@/lib/api";
import { principalDisplay } from "@/lib/utils";
import { ChatMessage, ChatSession, Principal, SourceItem } from "@/types";

export default function OperationsConsolePage() {
  // 1. State
  const [principals, setPrincipals] = useState<Principal[]>(DEMO_PRINCIPALS);
  const [currentPrincipal, setCurrentPrincipal] = useState<Principal>(DEMO_PRINCIPALS[0]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [isProcessingAction, setIsProcessingAction] = useState(false);
  const [apiHealthOk, setApiHealthOk] = useState(true);
  // The dataset snapshot the API is serving -- "now" for every answer.
  const [snapshot, setSnapshot] = useState<string | null>(null);

  // Context Panel State
  const [isContextOpen, setIsContextOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<ContextTab>("evidence");
  const [selectedSource, setSelectedSource] = useState<SourceItem | null>(null);

  // Mobile drawer states
  const [isSidebarOpenMobile, setIsSidebarOpenMobile] = useState(false);

  // 2. Initialize Sessions and API health on mount
  useEffect(() => {
    // The inspector is docked at >=1024px and an overlay drawer below that, so
    // it only starts open where it has a column of its own.
    setIsContextOpen(window.innerWidth >= 1024);

    // Check API Health
    fetch(apiUrl("/api/health"))
      .then((res) => setApiHealthOk(res.ok))
      .catch(() => setApiHealthOk(false));

    // Fetch demo principals if available
    fetch(apiUrl("/api/demo-principals"))
      .then((res) => res.json())
      .then((data: Principal[]) => {
        if (data && data.length > 0) {
          setPrincipals(data);
          setCurrentPrincipal(data[0]);
        }
      })
      .catch(() => {
        // Fallback to local constants
      });

    // The snapshot rides along on the accounts payload the API already serves.
    fetch(apiUrl("/api/accounts"))
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.snapshot) setSnapshot(data.snapshot);
      })
      .catch(() => {
        // Sidebar falls back to "Awaiting API".
      });

    // Load sessions from localStorage
    const saved = localStorage.getItem("parcelpilot_sessions");
    if (saved) {
      try {
        const parsed = JSON.parse(saved) as ChatSession[];
        if (parsed.length > 0) {
          setSessions(parsed);
          setActiveSessionId(parsed[0].id);
          return;
        }
      } catch {}
    }

    // Default initial session
    const initialSession: ChatSession = {
      id: "sess-" + Date.now(),
      title: "Support Copilot",
      messages: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      principal: DEMO_PRINCIPALS[0],
    };
    setSessions([initialSession]);
    setActiveSessionId(initialSession.id);
  }, []);

  // Save sessions to localStorage on change
  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem("parcelpilot_sessions", JSON.stringify(sessions));
    }
  }, [sessions]);

  // Keyboard Shortcuts (⌘N / Ctrl+N, Escape)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "n") {
        e.preventDefault();
        handleNewSession();
      }
      if (e.key === "Escape") {
        setIsSidebarOpenMobile(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [sessions]);

  // Active Session & Messages
  const activeSession = sessions.find((s) => s.id === activeSessionId) || sessions[0];
  const messages = activeSession ? activeSession.messages : [];

  // Active Sources and Trace (from last assistant message)
  const lastAssistantMessage = [...messages].reverse().find((m) => m.role === "assistant");
  const currentSources = lastAssistantMessage?.sources || [];
  const currentTrace = lastAssistantMessage?.tool_trace || [];
  const currentConfidence = lastAssistantMessage?.error ? null : lastAssistantMessage?.confidence ?? null;

  // Handlers
  const handleNewSession = () => {
    const newSession: ChatSession = {
      id: "sess-" + Date.now(),
      title: "New Conversation",
      messages: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      principal: currentPrincipal,
    };
    setSessions([newSession, ...sessions]);
    setActiveSessionId(newSession.id);
    setSelectedSource(null);
    setIsSidebarOpenMobile(false);
  };

  const handleDeleteSession = (id: string) => {
    const remaining = sessions.filter((s) => s.id !== id);
    if (remaining.length === 0) {
      handleNewSession();
    } else {
      setSessions(remaining);
      if (activeSessionId === id) {
        setActiveSessionId(remaining[0].id);
      }
    }
  };

  const handleResetChat = () => {
    if (!activeSession) return;
    const updated = sessions.map((s) =>
      s.id === activeSessionId
        ? { ...s, messages: [], title: "Support Copilot", updatedAt: new Date().toISOString() }
        : s
    );
    setSessions(updated);
    setSelectedSource(null);
  };

  const handlePrincipalChange = (principal: Principal) => {
    setCurrentPrincipal(principal);
  };

  const handleSelectSource = (source: SourceItem) => {
    setSelectedSource(source);
    setActiveTab("evidence");
    setIsContextOpen(true);
  };

  const handleOpenActivity = () => {
    setActiveTab("activity");
    setIsContextOpen(true);
  };

  // Send Message
  const handleSendMessage = async (userText: string) => {
    if (!userText.trim() || isLoading || !activeSession) return;

    const userMessage: ChatMessage = {
      id: "msg-" + Date.now(),
      role: "user",
      content: userText,
      timestamp: new Date().toISOString(),
    };

    // Update Session with User Message & Title
    const newTitle =
      activeSession.messages.length === 0
        ? userText.slice(0, 32) + (userText.length > 32 ? "…" : "")
        : activeSession.title;

    const updatedWithUser = sessions.map((s) =>
      s.id === activeSessionId
        ? {
            ...s,
            title: newTitle,
            messages: [...s.messages, userMessage],
            updatedAt: new Date().toISOString(),
          }
        : s
    );
    setSessions(updatedWithUser);
    setIsLoading(true);

    try {
      const response = await fetch(apiUrl("/api/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userText,
          principal: currentPrincipal,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        // Surfaced verbatim: a 403 scope denial and a 503 planner outage are
        // both meaningful to the operator, so the API's own detail is the text.
        const errorAssistantMsg: ChatMessage = {
          id: "msg-" + Date.now(),
          role: "assistant",
          content:
            data.detail ||
            `ParcelPilot could not complete this request (HTTP ${response.status}).`,
          error: true,
          timestamp: new Date().toISOString(),
        };
        setSessions((prev) =>
          prev.map((s) =>
            s.id === activeSessionId
              ? { ...s, messages: [...s.messages, errorAssistantMsg] }
              : s
          )
        );
        return;
      }

      const assistantMessage: ChatMessage = {
        id: "msg-" + Date.now(),
        role: "assistant",
        content: data.answer || "No response text received.",
        confidence: data.confidence || "low",
        tool_trace: data.tool_trace || [],
        sources: data.sources || [],
        pending_action: data.pending_action || null,
        timestamp: new Date().toISOString(),
      };

      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId
            ? {
                ...s,
                messages: [...s.messages, assistantMessage],
                updatedAt: new Date().toISOString(),
              }
            : s
        )
      );

      // If sources returned, preselect the first so the Evidence panel is populated
      setSelectedSource(data.sources && data.sources.length > 0 ? data.sources[0] : null);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: "msg-" + Date.now(),
        role: "assistant",
        content: `Could not reach the ParcelPilot API (${err.message}). Check that the backend is running and reachable from this browser.`,
        error: true,
        timestamp: new Date().toISOString(),
      };
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId ? { ...s, messages: [...s.messages, errorMsg] } : s
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  // Confirm Staged Escalation Flow
  const handleConfirmEscalation = async (token: string) => {
    if (!token || isProcessingAction) return;
    setIsProcessingAction(true);

    try {
      const res = await fetch(apiUrl("/api/actions/confirm"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          confirmation_token: token,
          principal: currentPrincipal,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setSessions((prev) =>
          prev.map((s) =>
            s.id === activeSessionId
              ? {
                  ...s,
                  messages: [
                    ...s.messages,
                    {
                      id: "msg-" + Date.now(),
                      role: "assistant" as const,
                      content:
                        data.detail || `The escalation was not recorded (HTTP ${res.status}).`,
                      error: true,
                      timestamp: new Date().toISOString(),
                    },
                  ],
                }
              : s
          )
        );
        return;
      }

      // Update message in session in-place
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== activeSessionId) return s;
          const updatedMessages = s.messages.map((m) => {
            if (m.pending_action?.confirmation_token === token) {
              return {
                ...m,
                pending_action: null,
                confirmed_record: data.record,
              };
            }
            return m;
          });
          return { ...s, messages: updatedMessages };
        })
      );
    } catch (err: any) {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId
            ? {
                ...s,
                messages: [
                  ...s.messages,
                  {
                    id: "msg-" + Date.now(),
                    role: "assistant" as const,
                    content: `Could not reach the ParcelPilot API to confirm (${err.message}). Nothing was recorded.`,
                    error: true,
                    timestamp: new Date().toISOString(),
                  },
                ],
              }
            : s
        )
      );
    } finally {
      setIsProcessingAction(false);
    }
  };

  // Select a preset scenario
  const handleSelectScenario = (prompt: string, recommendedPrincipalId?: string) => {
    if (recommendedPrincipalId) {
      const matched = principals.find((p) => p.user_id === recommendedPrincipalId);
      if (matched) setCurrentPrincipal(matched);
    }
    handleSendMessage(prompt);
  };

  return (
    <div className="flex h-screen w-screen bg-[var(--app-bg)] text-[var(--text)] overflow-hidden">
      {/* Mobile Sidebar Backdrop */}
      {isSidebarOpenMobile && (
        <div
          onClick={() => setIsSidebarOpenMobile(false)}
          className="fixed inset-0 bg-black/60 z-40 md:hidden transition-opacity"
        />
      )}

      {/* 1. LEFT NAVIGATION */}
      <div
        className={`fixed inset-y-0 left-0 z-50 md:static md:z-auto transition-transform duration-200 ease-in-out ${
          isSidebarOpenMobile ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
      >
        <Sidebar
          principals={principals}
          currentPrincipal={currentPrincipal}
          onPrincipalChange={handlePrincipalChange}
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelectSession={(id) => {
            setActiveSessionId(id);
            setSelectedSource(null);
            setIsSidebarOpenMobile(false);
          }}
          onNewSession={handleNewSession}
          onDeleteSession={handleDeleteSession}
          onSelectScenario={(prompt, principalId) => {
            handleSelectScenario(prompt, principalId);
            setIsSidebarOpenMobile(false);
          }}
          apiHealthOk={apiHealthOk}
          snapshot={snapshot}
          onViewSnapshotDetails={() => {
            setActiveTab("account");
            setIsContextOpen(true);
            setIsSidebarOpenMobile(false);
          }}
        />
      </div>

      {/* 2. CONVERSATION WORKSPACE */}
      <div className="flex-1 flex flex-col min-w-0 bg-[var(--main)]">
        <Header
          sessionTitle={activeSession?.title || "Support Copilot"}
          currentPrincipal={currentPrincipal}
          onResetChat={handleResetChat}
          isContextOpen={isContextOpen}
          onToggleContext={() => setIsContextOpen(!isContextOpen)}
          onToggleSidebarMobile={() => setIsSidebarOpenMobile(true)}
        />

        <Conversation
          messages={messages}
          isLoading={isLoading}
          onSelectPrompt={handleSendMessage}
          onSelectSource={handleSelectSource}
          onOpenActivity={handleOpenActivity}
          onConfirmEscalation={handleConfirmEscalation}
          isProcessingAction={isProcessingAction}
          selectedSource={selectedSource}
          userInitials={principalDisplay(currentPrincipal).name}
        />

        <Composer onSendMessage={handleSendMessage} isLoading={isLoading} />
      </div>

      {/* 3. CONTEXT INSPECTOR */}
      {isContextOpen && (
        <div className="w-[400px] shrink-0 h-full hidden lg:block">
          <ContextPanel
            currentPrincipal={currentPrincipal}
            sources={currentSources}
            selectedSource={selectedSource}
            toolTrace={currentTrace}
            confidence={currentConfidence}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            onSelectSource={handleSelectSource}
            onSelectPrompt={handleSendMessage}
            onClose={() => setIsContextOpen(false)}
          />
        </div>
      )}

      {/* Tablet/Mobile drawer for the inspector */}
      {isContextOpen && (
        <div
          onClick={() => setIsContextOpen(false)}
          className="fixed inset-0 bg-black/60 z-40 lg:hidden"
        />
      )}
      {isContextOpen && (
        <div className="fixed inset-y-0 right-0 z-50 w-[320px] max-w-[85vw] lg:hidden shadow-2xl shadow-black/50">
          <ContextPanel
            currentPrincipal={currentPrincipal}
            sources={currentSources}
            selectedSource={selectedSource}
            toolTrace={currentTrace}
            confidence={currentConfidence}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            onSelectSource={handleSelectSource}
            onSelectPrompt={handleSendMessage}
            onClose={() => setIsContextOpen(false)}
          />
        </div>
      )}
    </div>
  );
}
