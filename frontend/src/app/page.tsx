"use client";

import { useState, useRef } from "react";

export default function Home() {
  const [query, setQuery] = useState("");
  const [messages, setMessages] = useState<{role: string, content: string, citations?: string[], trace?: string[]}[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setUploading(true);
    try {
      // 1. Get presigned URL from FastAPI backend
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/v1/documents/upload-url?filename=${encodeURIComponent(file.name)}`, {
        method: 'POST'
      });
      const data = await res.json();
      
      if (!res.ok) throw new Error(data.detail || 'Failed to get upload URL');
      
      const { upload_url } = data;
      
      // 2. Upload file directly to S3 Bucket via signed URL
      const s3Res = await fetch(upload_url, {
        method: 'PUT',
        body: file,
        headers: {
          'Content-Type': 'application/pdf'
        }
      });
      
      if (s3Res.ok) {
        alert("Upload successful! Your document is now securely on AWS S3, triggering the Serverless ingestion pipeline.");
      } else {
        alert("Upload to S3 failed. Please verify your AWS IAM bucket permissions.");
      }
    } catch (err: any) {
      alert(`Error: ${err.message}`);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query) return;
    
    setMessages(prev => [...prev, { role: "user", content: query }]);
    setLoading(true);
    setQuery("");
    
    try {
      // MOCK of actual LangGraph execution output for UI visualization
      setTimeout(() => {
        setMessages(prev => [...prev, { 
          role: "assistant", 
          content: `Based on a multi-step analysis across the provided knowledge graph and documents, here is the synthesized answer: The primary risk factors highlighted in Q3 directly correlate with recent supply-chain disruptions noted in the generic framework documents.`,
          citations: ["Q3_Financials.pdf (pg 4)", "Technical_Architecture.md (chunk_id: 112)"],
          trace: [
            "[Retrieve Node] Successfully queried PGVector, identifying 5 semantically related chunks.", 
            "[Reason Node] Applied Chain of Thought reasoning. Identified contradiction in chunk 2 and aligned facts with chunk 1.", 
            "[Verify Node] Verification PASSED. Hallucination check cleared against baseline rules."
          ]
        }]);
        setLoading(false);
      }, 2000);
      
    } catch (err) {
      console.error(err);
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-gray-50 text-gray-900 font-sans">
      <div className="w-1/4 bg-white border-r border-gray-200 p-6 flex flex-col">
        <h2 className="text-2xl font-bold mb-8 text-indigo-600">RAG+</h2>
        
        <div className="mb-8">
          <h3 className="font-semibold text-gray-700 mb-4">Document Ingestion</h3>
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileUpload}
            className="hidden" 
            accept=".pdf,.txt,.md"
          />
          <div 
            onClick={() => fileInputRef.current?.click()}
            className={`p-6 border-2 border-dashed border-gray-300 rounded-lg text-center cursor-pointer hover:bg-gray-50 transition-colors ${uploading ? 'opacity-50 pointer-events-none' : ''}`}
          >
            <svg className="w-8 h-8 text-gray-400 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path></svg>
            <span className="text-sm text-gray-600 font-medium">{uploading ? 'Uploading to Live S3...' : 'Upload Document to AWS'}</span>
            <p className="text-xs text-gray-400 mt-1">Triggers async SQS Lambda</p>
          </div>
        </div>
        
        <div className="flex-1">
          <h3 className="font-semibold text-gray-700 mb-4">Indexed Database</h3>
          <ul className="space-y-3 text-sm text-gray-600">
            <li className="flex items-center p-2 hover:bg-gray-50 rounded-md">
              <span className="w-2 h-2 rounded-full bg-green-500 mr-3"></span> 
              <span className="flex-1 truncate">Q3_Financials.pdf</span>
              <span className="text-xs text-gray-400">Ready</span>
            </li>
            <li className="flex items-center p-2 hover:bg-gray-50 rounded-md">
              <span className="w-2 h-2 rounded-full bg-green-500 mr-3"></span> 
              <span className="flex-1 truncate">HR_Policy_2026.docx</span>
              <span className="text-xs text-gray-400">Ready</span>
            </li>
          </ul>
        </div>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="p-6 border-b border-gray-200 bg-white shadow-sm flex items-center justify-between z-10">
          <h1 className="text-xl font-semibold text-gray-800">Reasoning Workspace</h1>
          <div className="flex items-center space-x-4">
            <div className="px-3 py-1 bg-indigo-50 text-indigo-700 rounded-full text-xs font-medium">Tenant: Acme Corp</div>
            <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-sm font-bold text-gray-600">A</div>
          </div>
        </div>
        
        <div className="flex-1 p-6 overflow-y-auto w-full max-w-5xl mx-auto space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-gray-400">
              <div className="w-16 h-16 mb-4 rounded-full bg-gray-100 flex items-center justify-center">
                <svg className="w-8 h-8 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"></path></svg>
              </div>
              <p className="text-lg">Ask a complex question to initiate multi-step reasoning.</p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`p-5 rounded-2xl shadow-sm ${msg.role === 'user' ? 'bg-indigo-600 text-white max-w-2xl rounded-tr-sm' : 'bg-white border border-gray-200 max-w-4xl rounded-tl-sm'}`}>
                  <p className={`text-[15px] leading-relaxed ${msg.role === 'user' ? 'text-white' : 'text-gray-800'}`}>{msg.content}</p>
                  
                  {msg.trace && (
                    <div className="mt-5 p-4 bg-gray-50 rounded-xl border border-gray-100 text-sm">
                      <p className="font-semibold text-gray-700 mb-3 flex items-center">
                        <svg className="w-4 h-4 mr-2 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                        LangGraph Reasoning Trace
                      </p>
                      <ul className="space-y-2 text-gray-600">
                        {msg.trace.map((t, i) => (
                          <li key={i} className="flex items-start">
                            <span className="text-indigo-400 mr-2 font-bold">↳</span>
                            <span className="leading-snug">{t}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {msg.citations && (
                    <div className="mt-4 pt-4 border-t border-gray-100">
                      <p className="text-xs font-bold tracking-wider text-gray-400 uppercase mb-2">Verified Citations</p>
                      <div className="flex gap-2 flex-wrap">
                        {msg.citations.map((c, i) => (
                          <span key={i} className="px-2.5 py-1.5 bg-indigo-50 text-indigo-700 rounded-md text-xs font-medium border border-indigo-100 cursor-pointer hover:bg-indigo-100 transition-colors">{c}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
          {loading && (
             <div className="flex justify-start">
               <div className="p-4 rounded-2xl bg-white border border-gray-200 flex items-center shadow-sm rounded-tl-sm">
                 <div className="flex space-x-2 mr-3">
                   <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                   <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                   <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                 </div>
                 <span className="text-sm font-medium text-gray-500">Autonomous Agents are reasoning...</span>
               </div>
             </div>
          )}
        </div>
        
        <div className="p-6 bg-white border-t border-gray-200">
          <form onSubmit={handleQuery} className="max-w-4xl mx-auto relative">
            <input 
              type="text" 
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full pl-6 pr-32 py-4 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent shadow-sm text-gray-800 bg-gray-50 hover:bg-white transition-colors"
              placeholder="Ask a question..."
              disabled={loading}
            />
            <button 
              type="submit" 
              className={`absolute right-2 top-2 bottom-2 px-6 bg-indigo-600 text-white rounded-lg font-semibold shadow-sm hover:bg-indigo-700 transition-colors ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
              disabled={loading}
            >
              Analyze
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
