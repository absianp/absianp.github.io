"""
앱시안(absian) 블로그 게시글 전용 고해상도 SVG 썸네일 자동 생성 모듈
1200x630 규격, 다크 사이버/테크 감성, 11대 테마별 벡터 일러스트레이션 지원
"""
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "blog-frontend" / "public" / "images" / "thumbnails"

CATEGORY_CONFIG = {
    "개발 & 테크": {
        "bg_stops": [("#0a0f1d", "0%"), ("#0f172a", "50%"), ("#030712", "100%")],
        "accent": "#38bdf8",
        "pill_bg": "#0c4a6e",
        "pill_border": "#0284c7",
        "pill_text": "#bae6fd",
        "badge": "★ 2026 테크 실무"
    },
    "AI & 생산성": {
        "bg_stops": [("#130e24", "0%"), ("#1e1b4b", "50%"), ("#090514", "100%")],
        "accent": "#a855f7",
        "pill_bg": "#3b0764",
        "pill_border": "#9333ea",
        "pill_text": "#f3e8ff",
        "badge": "★ AI 생산성 가이드"
    },
    "스마트 부업 & 재테크": {
        "bg_stops": [("#06281e", "0%"), ("#064e3b", "50%"), ("#021510", "100%")],
        "accent": "#34d399",
        "pill_bg": "#064e3b",
        "pill_border": "#10b981",
        "pill_text": "#a7f3d0",
        "badge": "★ 고수익 부업 공식"
    },
    "스마트 부업": {
        "bg_stops": [("#06281e", "0%"), ("#064e3b", "50%"), ("#021510", "100%")],
        "accent": "#34d399",
        "pill_bg": "#064e3b",
        "pill_border": "#10b981",
        "pill_text": "#a7f3d0",
        "badge": "★ 스마트 부업 전략"
    },
    "블로그 수익화": {
        "bg_stops": [("#1e1b0a", "0%"), ("#422006", "50%"), ("#0f0b02", "100%")],
        "accent": "#fbbf24",
        "pill_bg": "#451a03",
        "pill_border": "#f59e0b",
        "pill_text": "#fef3c7",
        "badge": "★ 애드센스 수익화"
    },
    "SEO & 마케팅": {
        "bg_stops": [("#0f172a", "0%"), ("#1e293b", "50%"), ("#090d16", "100%")],
        "accent": "#38bdf8",
        "pill_bg": "#1e3a8a",
        "pill_border": "#2563eb",
        "pill_text": "#bfdbfe",
        "badge": "★ 구글 검색 최적화"
    }
}

def escape_xml(s: str) -> str:
    return (str(s).replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;")
                  .replace('"', "&quot;")
                  .replace("'", "&apos;"))

def split_title(title: str, max_len=18):
    words = title.split()
    lines = []
    curr = ""
    for w in words:
        if len(curr + " " + w) > max_len and curr:
            lines.append(curr.strip())
            curr = w
        else:
            curr = (curr + " " + w).strip()
    if curr:
        lines.append(curr.strip())
    if len(lines) > 3:
        lines = lines[:2] + [lines[2] + "..."]
    return lines

def classify_post(post_data: Dict[str, Any]) -> str:
    title = post_data.get("title", "")
    slug = post_data.get("slug", "")
    tags = post_data.get("tags", [])
    cat = post_data.get("category", "")
    t_text = (title + " " + slug).lower()

    if any(k in t_text for k in ["docker", "도커", "podman", "kubernetes", "쿠버네티스", "k8s", "helm", "cka"]):
        return "theme_docker_k8s"
    if any(k in t_text for k in ["aws", "cloud", "클라우드", "terraform", "테라폼", "cloudflare", "vercel"]):
        return "theme_cloud_aws"
    if any(k in t_text for k in ["github actions", "github", "git", "ci/cd", "깃허브"]):
        return "theme_github_cicd"
    if any(k in t_text for k in ["fastapi", "python", "파이썬", "redis", "postgres", "mysql", "sql", "nginx", "rest api", "백엔드", "sqlite", "celery"]):
        return "theme_fastapi_db"
    if any(k in t_text for k in ["notion", "노션", "obsidian", "옵시디언", "pkm"]):
        return "theme_notion_obsidian"
    if any(k in t_text for k in ["seo", "aio", "geo", "색인", "인덱싱", "schema.org", "메타태그", "core web vitals"]):
        return "theme_seo_aio"
    if any(k in t_text for k in ["etf", "isa", "irp", "연금", "주식", "배당", "재테크", "절세", "투자", "금융"]):
        return "theme_finance_etf"
    if any(k in t_text for k in ["chatgpt", "gpt", "claude", "gemini", "llm", "ollama", "prompt", "프롬프트", 
                                "midjourney", "미드저니", "stable diffusion", "스테이블", "copilot", "perplexity", 
                                "elevenlabs", "sora", "runway", "autogpt", "crewai", "rag", "langchain", 
                                "llamaindex", "deepseek", "litellm", "ai", "인공지능"]):
        return "theme_ai_llm"
    if any(k in t_text for k in ["부업", "전자책", "유튜브", "쇼츠", "크몽", "탈잉", "패시브", "gumroad", "flutterflow", "n8n", "스마트 부업"]):
        return "theme_side_hustle"
    if any(k in t_text for k in ["애드센스", "adsense", "cpc", "rpm", "광고"]):
        return "theme_adsense"

    if "AI" in cat:
        return "theme_ai_llm"
    if "개발" in cat or "테크" in cat:
        return "theme_generic_tech"
    if "부업" in cat or "재테크" in cat:
        return "theme_side_hustle"

    return "theme_generic_tech"

def get_theme_artwork(theme: str) -> str:
    if theme == "theme_ai_llm":
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#a855f7" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#c084fc" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#9333ea" stroke-width="2"/>
            <line x1="-70" y1="-50" x2="0" y2="-90" stroke="#a855f7" stroke-width="2" opacity="0.6"/>
            <line x1="70" y1="-50" x2="0" y2="-90" stroke="#a855f7" stroke-width="2" opacity="0.6"/>
            <line x1="-70" y1="-50" x2="0" y2="0" stroke="#38bdf8" stroke-width="2" opacity="0.7"/>
            <line x1="70" y1="-50" x2="0" y2="0" stroke="#38bdf8" stroke-width="2" opacity="0.7"/>
            <line x1="-70" y1="50" x2="0" y2="0" stroke="#38bdf8" stroke-width="2" opacity="0.7"/>
            <line x1="70" y1="50" x2="0" y2="0" stroke="#38bdf8" stroke-width="2" opacity="0.7"/>
            <line x1="-70" y1="50" x2="0" y2="90" stroke="#a855f7" stroke-width="2" opacity="0.6"/>
            <line x1="70" y1="50" x2="0" y2="90" stroke="#a855f7" stroke-width="2" opacity="0.6"/>
            <circle cx="-70" cy="-50" r="14" fill="#3b0764" stroke="#c084fc" stroke-width="2"/>
            <circle cx="70" cy="-50" r="14" fill="#082f49" stroke="#38bdf8" stroke-width="2"/>
            <circle cx="-70" cy="50" r="14" fill="#082f49" stroke="#38bdf8" stroke-width="2"/>
            <circle cx="70" cy="50" r="14" fill="#3b0764" stroke="#c084fc" stroke-width="2"/>
            <circle cx="0" cy="-90" r="12" fill="#1e1b4b" stroke="#818cf8" stroke-width="2"/>
            <circle cx="0" cy="90" r="12" fill="#1e1b4b" stroke="#818cf8" stroke-width="2"/>
            <rect x="-48" y="-48" width="96" height="96" rx="20" fill="#1e1b4b" stroke="url(#accentGrad)" stroke-width="3" filter="url(#dropShadow)"/>
            <line x1="-30" y1="-56" x2="-30" y2="-48" stroke="#38bdf8" stroke-width="3"/>
            <line x1="0" y1="-56" x2="0" y2="-48" stroke="#38bdf8" stroke-width="3"/>
            <line x1="30" y1="-56" x2="30" y2="-48" stroke="#38bdf8" stroke-width="3"/>
            <line x1="-30" y1="48" x2="-30" y2="56" stroke="#38bdf8" stroke-width="3"/>
            <line x1="0" y1="48" x2="0" y2="56" stroke="#38bdf8" stroke-width="3"/>
            <line x1="30" y1="48" x2="30" y2="56" stroke="#38bdf8" stroke-width="3"/>
            <text x="0" y="8" font-family="'Pretendard', sans-serif" font-size="28" font-weight="900" fill="#f3e8ff" text-anchor="middle" letter-spacing="1">AI</text>
            <text x="0" y="24" font-family="'Pretendard', sans-serif" font-size="10" font-weight="700" fill="#38bdf8" text-anchor="middle" letter-spacing="2">LLM CORE</text>
            <g transform="translate(60, -95)">
                <rect x="-40" y="-14" width="80" height="28" rx="14" fill="#3b0764" stroke="#a855f7" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#f5d0fe" text-anchor="middle">PROMPT</text>
            </g>
            <g transform="translate(-60, 95)">
                <rect x="-45" y="-14" width="90" height="28" rx="14" fill="#082f49" stroke="#38bdf8" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#bae6fd" text-anchor="middle">RAG AGENT</text>
            </g>
        </g>
        """
    elif theme == "theme_docker_k8s":
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#0284c7" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#38bdf8" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#0284c7" stroke-width="2"/>
            <circle cx="0" cy="-20" r="55" fill="none" stroke="#326ce5" stroke-width="5"/>
            <circle cx="0" cy="-20" r="22" fill="#1e3a8a" stroke="#60a5fa" stroke-width="3"/>
            <line x1="0" y1="-75" x2="0" y2="35" stroke="#326ce5" stroke-width="4"/>
            <line x1="-50" y1="-35" x2="50" y2="-5" stroke="#326ce5" stroke-width="4"/>
            <line x1="-45" y1="10" x2="45" y2="-50" stroke="#326ce5" stroke-width="4"/>
            <g transform="translate(0, 50)">
                <path d="M-80 20 C-60 10 60 10 80 20 L70 35 L-70 35 Z" fill="#0ea5e9" opacity="0.85"/>
                <rect x="-45" y="-5" width="26" height="18" rx="3" fill="#38bdf8" stroke="#0284c7" stroke-width="1.5"/>
                <rect x="-13" y="-5" width="26" height="18" rx="3" fill="#38bdf8" stroke="#0284c7" stroke-width="1.5"/>
                <rect x="19" y="-5" width="26" height="18" rx="3" fill="#38bdf8" stroke="#0284c7" stroke-width="1.5"/>
                <rect x="-29" y="-27" width="26" height="18" rx="3" fill="#7dd3fc" stroke="#0284c7" stroke-width="1.5"/>
                <rect x="3" y="-27" width="26" height="18" rx="3" fill="#7dd3fc" stroke="#0284c7" stroke-width="1.5"/>
            </g>
            <g transform="translate(75, -80)">
                <rect x="-35" y="-14" width="70" height="28" rx="14" fill="#1e3a8a" stroke="#60a5fa" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#dbeafe" text-anchor="middle">K8S</text>
            </g>
            <g transform="translate(-75, -80)">
                <rect x="-42" y="-14" width="84" height="28" rx="14" fill="#082f49" stroke="#38bdf8" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#bae6fd" text-anchor="middle">DOCKER</text>
            </g>
        </g>
        """
    elif theme == "theme_cloud_aws":
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#f97316" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#fb923c" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#ea580c" stroke-width="2"/>
            <path d="M-60 10 A35 35 0 0 1 -10 -35 A45 45 0 0 1 55 -25 A35 35 0 0 1 70 15 A30 30 0 0 1 45 45 L-40 45 A30 30 0 0 1 -60 10 Z" fill="#1e293b" stroke="#ff9900" stroke-width="3" filter="url(#dropShadow)"/>
            <rect x="-35" y="-12" width="70" height="14" rx="4" fill="#0f172a" stroke="#64748b" stroke-width="1.5"/>
            <circle cx="-25" cy="-5" r="2.5" fill="#10b981"/>
            <circle cx="-16" cy="-5" r="2.5" fill="#38bdf8"/>
            <rect x="-35" y="6" width="70" height="14" rx="4" fill="#0f172a" stroke="#64748b" stroke-width="1.5"/>
            <circle cx="-25" cy="13" r="2.5" fill="#10b981"/>
            <circle cx="-16" cy="13" r="2.5" fill="#38bdf8"/>
            <rect x="-35" y="24" width="70" height="14" rx="4" fill="#0f172a" stroke="#64748b" stroke-width="1.5"/>
            <circle cx="-25" cy="31" r="2.5" fill="#10b981"/>
            <circle cx="-16" cy="31" r="2.5" fill="#f59e0b"/>
            <g transform="translate(65, -75)">
                <polygon points="0,-18 16,-8 0,2 -16,-8" fill="#5c4ee5"/>
                <polygon points="-16,-8 0,2 0,22 -16,12" fill="#4033b0"/>
                <polygon points="16,-8 0,2 0,22 16,12" fill="#7567ff"/>
            </g>
            <g transform="translate(0, 95)">
                <rect x="-55" y="-14" width="110" height="28" rx="14" fill="#431407" stroke="#ff9900" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#fed7aa" text-anchor="middle">AWS CLOUD INFRA</text>
            </g>
        </g>
        """
    elif theme == "theme_github_cicd":
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#8b5cf6" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#a78bfa" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#7c3aed" stroke-width="2"/>
            <line x1="-80" y1="20" x2="80" y2="20" stroke="#a78bfa" stroke-width="4"/>
            <circle cx="-70" cy="20" r="9" fill="#2e1065" stroke="#a78bfa" stroke-width="3"/>
            <circle cx="-10" cy="20" r="9" fill="#2e1065" stroke="#a78bfa" stroke-width="3"/>
            <circle cx="65" cy="20" r="10" fill="#10b981" stroke="#ffffff" stroke-width="2.5"/>
            <path d="M-70 20 Q-40 -40 0 -40 Q40 -40 65 20" fill="none" stroke="#38bdf8" stroke-width="3.5" stroke-dasharray="5,3"/>
            <circle cx="0" cy="-40" r="9" fill="#082f49" stroke="#38bdf8" stroke-width="3"/>
            <g transform="translate(0, -38)">
                <polygon points="-4,-9 3,-9 0,-2 5,-2 -3,9 -1,1 -5,1" fill="#fbbf24"/>
            </g>
            <g transform="translate(65, 20)">
                <path d="M-4 0 L-1 4 L5 -4" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round"/>
            </g>
            <g transform="translate(0, 85)">
                <rect x="-65" y="-14" width="130" height="28" rx="14" fill="#2e1065" stroke="#a855f7" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#e9d5ff" text-anchor="middle">GITHUB ACTIONS CI/CD</text>
            </g>
            <g transform="translate(-50, -85)">
                <rect x="-35" y="-14" width="70" height="28" rx="14" fill="#052e16" stroke="#10b981" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#a7f3d0" text-anchor="middle">PASS 100%</text>
            </g>
        </g>
        """
    elif theme == "theme_fastapi_db":
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#0284c7" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#38bdf8" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#0284c7" stroke-width="2"/>
            <g transform="translate(-35, 10)">
                <path d="M-40 25 C-40 38 40 38 40 25 L40 45 C40 58 -40 58 -40 45 Z" fill="#1e3a8a" stroke="#60a5fa" stroke-width="2"/>
                <ellipse cx="0" cy="25" rx="40" ry="12" fill="#2563eb" stroke="#60a5fa" stroke-width="2"/>
                <path d="M-40 0 C-40 13 40 13 40 0 L40 20 C40 33 -40 33 -40 20 Z" fill="#1e3a8a" stroke="#60a5fa" stroke-width="2"/>
                <ellipse cx="0" cy="0" rx="40" ry="12" fill="#2563eb" stroke="#60a5fa" stroke-width="2"/>
                <path d="M-40 -25 C-40 -12 40 -12 40 -25 L40 -5 C40 8 -40 8 -40 -5 Z" fill="#1e3a8a" stroke="#60a5fa" stroke-width="2"/>
                <ellipse cx="0" cy="-25" rx="40" ry="12" fill="#38bdf8" stroke="#60a5fa" stroke-width="2"/>
            </g>
            <g transform="translate(45, -25)">
                <circle cx="0" cy="0" r="32" fill="#042f2e" stroke="#059669" stroke-width="2.5" filter="url(#dropShadow)"/>
                <polygon points="-5,-16 6,-16 0,-3 9,-3 -7,18 -3,3 -10,3" fill="#34d399"/>
            </g>
            <g transform="translate(50, 45)">
                <rect x="-30" y="-12" width="60" height="24" rx="12" fill="#1e293b" stroke="#facc15" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#fef08a" text-anchor="middle">PYTHON</text>
            </g>
            <g transform="translate(0, 95)">
                <rect x="-55" y="-14" width="110" height="28" rx="14" fill="#082f49" stroke="#38bdf8" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#bae6fd" text-anchor="middle">REST API &amp; DB</text>
            </g>
        </g>
        """
    elif theme == "theme_notion_obsidian":
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#8b5cf6" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#c084fc" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#7c3aed" stroke-width="2"/>
            <g transform="translate(25, -20)">
                <line x1="-40" y1="-30" x2="0" y2="0" stroke="#a78bfa" stroke-width="2"/>
                <line x1="40" y1="-20" x2="0" y2="0" stroke="#a78bfa" stroke-width="2"/>
                <line x1="-30" y1="35" x2="0" y2="0" stroke="#a78bfa" stroke-width="2"/>
                <line x1="35" y1="30" x2="0" y2="0" stroke="#a78bfa" stroke-width="2"/>
                <line x1="-40" y1="-30" x2="-30" y2="35" stroke="#6d28d9" stroke-width="1.5" stroke-dasharray="3,3"/>
                <line x1="40" y1="-20" x2="35" y2="30" stroke="#6d28d9" stroke-width="1.5" stroke-dasharray="3,3"/>
                <circle cx="0" cy="0" r="14" fill="#7c3aed" stroke="#ffffff" stroke-width="2.5"/>
                <circle cx="-40" cy="-30" r="8" fill="#38bdf8"/>
                <circle cx="40" cy="-20" r="9" fill="#c084fc"/>
                <circle cx="-30" cy="35" r="7" fill="#34d399"/>
                <circle cx="35" cy="30" r="8" fill="#f43f5e"/>
            </g>
            <g transform="translate(-45, 10)">
                <rect x="-35" y="-35" width="70" height="70" rx="16" fill="#18181b" stroke="#e4e4e7" stroke-width="3" filter="url(#dropShadow)"/>
                <text x="0" y="14" font-family="'Pretendard', sans-serif" font-size="40" font-weight="900" fill="#ffffff" text-anchor="middle">N</text>
            </g>
            <g transform="translate(0, 95)">
                <rect x="-60" y="-14" width="120" height="28" rx="14" fill="#2e1065" stroke="#c084fc" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#f3e8ff" text-anchor="middle">PKM &amp; NOTION VAULT</text>
            </g>
        </g>
        """
    elif theme == "theme_seo_aio":
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#38bdf8" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#0ea5e9" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#0284c7" stroke-width="2"/>
            <g transform="translate(0, -60)">
                <rect x="-75" y="-18" width="150" height="36" rx="18" fill="#1e293b" stroke="#64748b" stroke-width="2"/>
                <circle cx="-52" cy="0" r="6" fill="none" stroke="#94a3b8" stroke-width="2"/>
                <line x1="-48" y1="4" x2="-43" y2="9" stroke="#94a3b8" stroke-width="2"/>
                <circle cx="35" cy="0" r="3" fill="#4285f4"/>
                <circle cx="44" cy="0" r="3" fill="#ea4335"/>
                <circle cx="53" cy="0" r="3" fill="#fbbc05"/>
                <circle cx="62" cy="0" r="3" fill="#34a853"/>
            </g>
            <g transform="translate(0, 15)">
                <rect x="-70" y="-30" width="140" height="60" rx="12" fill="#0c4a6e" stroke="#38bdf8" stroke-width="2" filter="url(#dropShadow)"/>
                <text x="-55" y="-12" font-family="'Pretendard', sans-serif" font-size="10" font-weight="800" fill="#7dd3fc">✨ AI OVERVIEW</text>
                <line x1="-55" y1="0" x2="45" y2="0" stroke="#38bdf8" stroke-width="3" stroke-linecap="round" opacity="0.8"/>
                <line x1="-55" y1="10" x2="20" y2="10" stroke="#bae6fd" stroke-width="2.5" stroke-linecap="round" opacity="0.6"/>
            </g>
            <g transform="translate(60, -85)">
                <circle cx="0" cy="0" r="20" fill="#eab308" stroke="#ffffff" stroke-width="2"/>
                <text x="0" y="6" font-family="'Pretendard', sans-serif" font-size="14" font-weight="900" fill="#18181b" text-anchor="middle">#1</text>
            </g>
            <g transform="translate(0, 95)">
                <rect x="-55" y="-14" width="110" height="28" rx="14" fill="#082f49" stroke="#38bdf8" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#bae6fd" text-anchor="middle">GOOGLE AIO / SEO</text>
            </g>
        </g>
        """
    elif theme == "theme_finance_etf":
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#10b981" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#34d399" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#059669" stroke-width="2"/>
            <line x1="-70" y1="45" x2="70" y2="45" stroke="#64748b" stroke-width="2.5"/>
            <line x1="-70" y1="45" x2="-70" y2="-55" stroke="#64748b" stroke-width="2.5"/>
            <line x1="-48" y1="20" x2="-48" y2="40" stroke="#34d399" stroke-width="1.5"/>
            <rect x="-54" y="24" width="12" height="12" rx="2" fill="#10b981"/>
            <line x1="-24" y1="5" x2="-24" y2="30" stroke="#34d399" stroke-width="1.5"/>
            <rect x="-30" y="10" width="12" height="15" rx="2" fill="#10b981"/>
            <line x1="0" y1="-20" x2="0" y2="15" stroke="#34d399" stroke-width="1.5"/>
            <rect x="-6" y="-12" width="12" height="20" rx="2" fill="#34d399"/>
            <line x1="24" y1="-50" x2="24" y2="-10" stroke="#34d399" stroke-width="1.5"/>
            <rect x="18" y="-42" width="12" height="24" rx="2" fill="#10b981"/>
            <path d="M-65 35 Q-10 25 50 -55" fill="none" stroke="#f59e0b" stroke-width="4"/>
            <circle cx="50" cy="-55" r="7" fill="#fbbf24" stroke="#ffffff" stroke-width="2"/>
            <g transform="translate(-40, -50)">
                <circle cx="0" cy="0" r="18" fill="url(#goldGrad)" stroke="#b45309" stroke-width="2"/>
                <text x="0" y="6" font-family="'Pretendard', sans-serif" font-size="15" font-weight="900" fill="#78350f" text-anchor="middle">₩</text>
            </g>
            <g transform="translate(0, 95)">
                <rect x="-55" y="-14" width="110" height="28" rx="14" fill="#064e3b" stroke="#10b981" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#a7f3d0" text-anchor="middle">ETF &amp; ISA 複利</text>
            </g>
        </g>
        """
    elif theme == "theme_adsense":
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#eab308" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#fde047" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#ca8a04" stroke-width="2"/>
            <g transform="translate(-40, -25)">
                <circle cx="0" cy="0" r="38" fill="url(#goldGrad)" stroke="#b45309" stroke-width="3" filter="url(#dropShadow)"/>
                <circle cx="0" cy="0" r="31" fill="none" stroke="#fef08a" stroke-width="1.5" stroke-dasharray="3,3"/>
                <text x="0" y="14" font-family="'Pretendard', sans-serif" font-size="42" font-weight="900" fill="#78350f" text-anchor="middle">$</text>
            </g>
            <g transform="translate(35, 10)">
                <rect x="-40" y="-35" width="80" height="70" rx="12" fill="#1e293b" stroke="#f59e0b" stroke-width="2"/>
                <text x="-30" y="-18" font-family="'Pretendard', sans-serif" font-size="10" font-weight="800" fill="#94a3b8">RPM</text>
                <text x="-30" y="5" font-family="'Pretendard', sans-serif" font-size="18" font-weight="900" fill="#34d399">$52.4</text>
                <rect x="-30" y="15" width="12" height="12" rx="2" fill="#38bdf8"/>
                <rect x="-14" y="10" width="12" height="17" rx="2" fill="#38bdf8"/>
                <rect x="2" y="2" width="12" height="25" rx="2" fill="#34d399"/>
            </g>
            <g transform="translate(45, -60)">
                <rect x="-35" y="-12" width="70" height="24" rx="12" fill="#064e3b" stroke="#10b981" stroke-width="1.5"/>
                <text x="0" y="4" font-family="'Pretendard', sans-serif" font-size="10" font-weight="900" fill="#a7f3d0" text-anchor="middle">CTR 3.8%</text>
            </g>
            <g transform="translate(0, 95)">
                <rect x="-60" y="-14" width="120" height="28" rx="14" fill="#451a03" stroke="#f59e0b" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#fef3c7" text-anchor="middle">ADSENSE HIGH RPM</text>
            </g>
        </g>
        """
    elif theme == "theme_side_hustle":
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#f43f5e" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#fb7185" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#e11d48" stroke-width="2"/>
            <g transform="translate(-20, -10) rotate(-45)">
                <path d="M0 -40 C15 -20 18 10 15 30 L-15 30 C-18 10 -15 -20 0 -40 Z" fill="#e2e8f0" stroke="#94a3b8" stroke-width="2"/>
                <circle cx="0" cy="-5" r="7" fill="#0284c7" stroke="#38bdf8" stroke-width="2"/>
                <path d="M-15 15 L-30 32 L-15 30 Z" fill="#f43f5e"/>
                <path d="M15 15 L30 32 L15 30 Z" fill="#f43f5e"/>
                <path d="M-10 32 Q0 55 10 32 Q0 45 -10 32" fill="#fbbf24"/>
            </g>
            <g transform="translate(45, 20)">
                <rect x="-28" y="-35" width="56" height="70" rx="8" fill="#1e293b" stroke="#f43f5e" stroke-width="2" filter="url(#dropShadow)"/>
                <text x="0" y="-10" font-family="'Pretendard', sans-serif" font-size="12" font-weight="900" fill="#fda4af" text-anchor="middle">PDF</text>
                <line x1="-18" y1="5" x2="18" y2="5" stroke="#64748b" stroke-width="2"/>
                <line x1="-18" y1="15" x2="8" y2="15" stroke="#64748b" stroke-width="2"/>
            </g>
            <g transform="translate(0, 95)">
                <rect x="-65" y="-14" width="130" height="28" rx="14" fill="#4c0519" stroke="#f43f5e" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#ffe4e6" text-anchor="middle">PASSIVE INCOME BUNDLE</text>
            </g>
        </g>
        """
    else:  # theme_generic_tech
        return """
        <g transform="translate(940, 315)">
            <circle cx="0" cy="0" r="190" fill="#2563eb" opacity="0.2" filter="url(#glowFilter)"/>
            <circle cx="0" cy="0" r="175" fill="#0f172a" stroke="#60a5fa" stroke-width="2.5" stroke-dasharray="8,6" opacity="0.8"/>
            <circle cx="0" cy="0" r="150" fill="url(#panelGrad)" stroke="#1d4ed8" stroke-width="2"/>
            <polygon points="0,-60 52,-30 52,30 0,60 -52,30 -52,-30" fill="#0f172a" stroke="#38bdf8" stroke-width="3" filter="url(#dropShadow)"/>
            <polygon points="0,-40 35,-20 35,20 0,40 -35,20 -35,-20" fill="#1e3a8a" stroke="#60a5fa" stroke-width="2"/>
            <text x="0" y="14" font-family="'Pretendard', monospace" font-size="34" font-weight="900" fill="#93c5fd" text-anchor="middle">&lt;/&gt;</text>
            <line x1="-52" y1="0" x2="-80" y2="0" stroke="#38bdf8" stroke-width="2"/>
            <circle cx="-80" cy="0" r="4" fill="#38bdf8"/>
            <line x1="52" y1="0" x2="80" y2="0" stroke="#38bdf8" stroke-width="2"/>
            <circle cx="80" cy="0" r="4" fill="#38bdf8"/>
            <line x1="0" y1="-60" x2="0" y2="-85" stroke="#38bdf8" stroke-width="2"/>
            <circle cx="0" cy="-85" r="4" fill="#38bdf8"/>
            <g transform="translate(0, 95)">
                <rect x="-60" y="-14" width="120" height="28" rx="14" fill="#1e3a8a" stroke="#60a5fa" stroke-width="2"/>
                <text x="0" y="5" font-family="'Pretendard', sans-serif" font-size="11" font-weight="900" fill="#dbeafe" text-anchor="middle">DEV &amp; TECH ARCH</text>
            </g>
        </g>
        """

def generate_svg_string(post: Dict[str, Any]) -> str:
    slug = post.get("slug", "")
    title = post.get("title", "")
    desc = post.get("description", "")
    category = post.get("category", "개발 & 테크")

    cfg = CATEGORY_CONFIG.get(category, CATEGORY_CONFIG["개발 & 테크"])
    bg_stops = cfg["bg_stops"]
    accent = cfg["accent"]
    pill_bg = cfg["pill_bg"]
    pill_border = cfg["pill_border"]
    pill_text = cfg["pill_text"]
    badge_text = cfg["badge"]

    theme = classify_post(post)
    artwork = get_theme_artwork(theme)

    title_lines = split_title(title, max_len=18)
    title_tspans = []
    line_height = 58
    for i, line in enumerate(title_lines):
        dy = 0 if i == 0 else line_height
        title_tspans.append(f'<tspan x="90" dy="{dy}">{escape_xml(line)}</tspan>')
    title_xml = "".join(title_tspans)

    y_start = 245 if len(title_lines) >= 3 else 275

    clean_desc = re.sub(r'[\r\n\t]+', ' ', desc).strip()
    if len(clean_desc) > 68:
        clean_desc = clean_desc[:65] + "..."
    if not clean_desc:
        clean_desc = "AI 실무, 개발 테크닉, 스마트 부업 핵심 인사이트를 담은 가이드입니다."
    desc_xml = escape_xml(clean_desc)

    return f"""<svg width="1200" height="630" viewBox="0 0 1200 630" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="mainBg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="{bg_stops[0][1]}" stop-color="{bg_stops[0][0]}" />
      <stop offset="{bg_stops[1][1]}" stop-color="{bg_stops[1][0]}" />
      <stop offset="{bg_stops[2][1]}" stop-color="{bg_stops[2][0]}" />
    </linearGradient>

    <linearGradient id="accentGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{accent}" />
      <stop offset="100%" stop-color="#ffffff" />
    </linearGradient>

    <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#f59e0b" />
      <stop offset="50%" stop-color="#fbbf24" />
      <stop offset="100%" stop-color="#fef08a" />
    </linearGradient>

    <linearGradient id="panelGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1e293b" stop-opacity="0.95" />
      <stop offset="100%" stop-color="#0f172a" stop-opacity="0.98" />
    </linearGradient>

    <filter id="glowFilter" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="40" result="blur" />
    </filter>

    <filter id="dropShadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#000000" flood-opacity="0.5" />
    </filter>
  </defs>

  <rect width="1200" height="630" fill="url(#mainBg)" />
  <circle cx="150" cy="120" r="280" fill="{accent}" opacity="0.12" filter="url(#glowFilter)" />
  <circle cx="1050" cy="480" r="320" fill="{accent}" opacity="0.14" filter="url(#glowFilter)" />

  <rect x="36" y="36" width="1128" height="558" rx="28" fill="none" stroke="{accent}" stroke-opacity="0.3" stroke-width="1.5" />
  <rect x="44" y="44" width="1112" height="542" rx="22" fill="none" stroke="#ffffff" stroke-opacity="0.06" stroke-width="1" />

  <g transform="translate(90, 85)">
    <rect x="0" y="0" width="46" height="46" rx="12" fill="{pill_bg}" stroke="{accent}" stroke-width="1.5" filter="url(#dropShadow)" />
    <path d="M12 16 L22 23 L12 30" fill="none" stroke="{accent}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
    <line x1="24" y1="30" x2="34" y2="30" stroke="#ffffff" stroke-width="3" stroke-linecap="round" />
    
    <text x="62" y="24" font-family="'Pretendard', sans-serif" font-size="22" font-weight="900" fill="#ffffff" letter-spacing="-0.5">앱시안</text>
    <text x="135" y="24" font-family="'Pretendard', sans-serif" font-size="15" font-weight="700" fill="{accent}" letter-spacing="-0.2">absian</text>
    <text x="62" y="42" font-family="'Pretendard', sans-serif" font-size="13" font-weight="500" fill="#94a3b8">AI &amp; 테크 · 개발 실무 · 스마트 부업</text>
  </g>

  <g transform="translate(90, 160)">
    <rect x="0" y="0" width="180" height="38" rx="19" fill="{pill_bg}" stroke="{pill_border}" stroke-width="2" />
    <text x="18" y="24" font-family="'Pretendard', sans-serif" font-size="15" font-weight="800" fill="{pill_text}">{escape_xml(category)}</text>

    <g transform="translate(192, 0)">
      <rect x="0" y="0" width="170" height="38" rx="19" fill="#1e293b" stroke="{accent}" stroke-width="1.5" />
      <text x="16" y="24" font-family="'Pretendard', sans-serif" font-size="14" font-weight="800" fill="#ffffff">{badge_text}</text>
    </g>
  </g>

  <text x="90" y="{y_start}" font-family="'Pretendard', sans-serif" font-size="46" font-weight="900" fill="#ffffff" letter-spacing="-1.5" filter="url(#dropShadow)">
    {title_xml}
  </text>

  <g transform="translate(90, 465)">
    <rect x="0" y="0" width="580" height="54" rx="14" fill="#0f172a" fill-opacity="0.85" stroke="#ffffff" stroke-opacity="0.12" stroke-width="1" />
    <rect x="0" y="0" width="6" height="54" rx="3" fill="{accent}" />
    <text x="24" y="33" font-family="'Pretendard', sans-serif" font-size="16" font-weight="500" fill="#e2e8f0">{desc_xml}</text>
  </g>

  <g transform="translate(90, 555)">
    <circle cx="6" cy="-5" r="4" fill="#10b981" />
    <text x="18" y="0" font-family="'Pretendard', sans-serif" font-size="14" font-weight="700" fill="{accent}">실무 코드 &amp; 팩트체크 완료</text>
    <text x="185" y="0" font-family="'Pretendard', sans-serif" font-size="14" font-weight="400" fill="#94a3b8">• absianp.github.io</text>
  </g>

  {artwork}
</svg>"""

def generate_thumbnail_for_post(post_data: Dict[str, Any], output_dir: Optional[str] = None) -> str:
    """새 글 등록 시 해당 글에 맞는 고유 SVG 썸네일을 파일로 생성하고 상대 경로 반환"""
    out_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = post_data.get("slug", "new-post")
    svg_str = generate_svg_string(post_data)
    file_path = out_dir / f"{slug}.svg"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(svg_str)
    return f"/images/thumbnails/{slug}.svg"
