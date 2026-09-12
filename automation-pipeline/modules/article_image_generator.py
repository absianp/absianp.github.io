"""
앱시안(absian) 본문 전용 설명 이해용 인포그래픽/다이어그램 이미지 자동 생성 모듈
- 글 본문의 핵심 설명 및 기술 아키텍처/워크플로우 이해를 돕는 고해상도 1536x1024 규격 이미지 2종 생성
- WebP 포맷으로 저장 및 Astro 마크다운 figure 태그 자동 삽입
- 개발/AI/클라우드/부업 실무 맞춤형 다크 사이버 테크 다이어그램 디자인
"""
import os
import re
import subprocess
from html import escape
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

BASE_DIR = Path(__file__).resolve().parents[2]
PUBLIC_IMG_DIR = BASE_DIR / "blog-frontend" / "public" / "images" / "articles"
DIST_IMG_DIR = BASE_DIR / "blog-frontend" / "dist" / "images" / "articles"

SITE_PREFIX = "absian"


def clean_text(text: str, max_len: int = 30) -> str:
    text = re.sub(r"[#*`_~]", "", text).strip()
    return text[:max_len] + ("..." if len(text) > max_len else "")


def extract_h2_sections(markdown_content: str) -> List[Tuple[str, str]]:
    """본문에서 H2 헤딩들과 해당 섹션의 첫 문장들을 추출"""
    sections = []
    lines = markdown_content.splitlines()
    curr_h2 = None
    curr_body = []

    for line in lines:
        if line.strip().startswith("## "):
            if curr_h2:
                body_sample = " ".join(curr_body).strip()
                sections.append((curr_h2, body_sample))
            curr_h2 = line.strip()
            curr_body = []
        elif curr_h2 and line.strip() and not line.strip().startswith("#") and not line.strip().startswith("<!--"):
            if len(curr_body) < 3:
                curr_body.append(line.strip())

    if curr_h2:
        body_sample = " ".join(curr_body).strip()
        sections.append((curr_h2, body_sample))

    return sections


def generate_tech_infographic_svg(
    title: str,
    subtitle: str,
    kind: str,  # 'architecture' or 'workflow' or 'comparison'
    category: str,
    step_items: List[Dict[str, str]]
) -> str:
    """1536x1024 규격의 모던 다크 사이버/테크 인포그래픽 SVG 생성"""
    
    # 카테고리별 테크 색상
    if "AI" in category:
        accent = "#a855f7"
        accent_sub = "#c084fc"
        card_border = "#9333ea"
        badge_text = "AI & ML 파이프라인 아키텍처"
    elif "부업" in category or "수익" in category:
        accent = "#34d399"
        accent_sub = "#6ee7b7"
        card_border = "#10b981"
        badge_text = "스마트 부업 & 자동화 워크플로우"
    elif "SEO" in category or "마케팅" in category:
        accent = "#38bdf8"
        accent_sub = "#7dd3fc"
        card_border = "#0284c7"
        badge_text = "AIO & 검색 엔진 인용 최적화 구조"
    else:
        accent = "#38bdf8"
        accent_sub = "#818cf8"
        card_border = "#2563eb"
        badge_text = "클라우드 & 개발 실무 아키텍처"

    # 카드 3개 레이아웃 구성
    cards_svg = ""
    card_width = 410
    card_height = 500
    start_x = 98
    card_y = 310

    for idx, item in enumerate(step_items[:3]):
        cx = start_x + idx * (card_width + 44)
        num_str = f"PHASE 0{idx + 1}"
        item_title = escape(clean_text(item.get("title", f"모듈 {idx + 1}"), 18))
        item_desc1 = escape(clean_text(item.get("desc1", "핵심 입력 및 데이터 파싱"), 25))
        item_desc2 = escape(clean_text(item.get("desc2", "비즈니스 로직 및 변환 처리"), 25))
        item_desc3 = escape(clean_text(item.get("desc3", "검증 완료 및 결과 출력"), 25))
        highlight = escape(clean_text(item.get("highlight", "핵심 구현 포인트"), 20))

        cards_svg += f"""
        <!-- 카드 {idx + 1} -->
        <g transform="translate({cx}, {card_y})">
            <!-- 카드 배경 -->
            <rect width="{card_width}" height="{card_height}" rx="24" fill="#0f172a" fill-opacity="0.95" stroke="{card_border}" stroke-width="2" filter="url(#dropShadow)" />
            
            <!-- 상단 페이즈 뱃지 -->
            <g transform="translate(32, 32)">
                <rect width="110" height="36" rx="10" fill="#1e293b" stroke="{accent}" stroke-width="1.5" />
                <text x="55" y="24" font-family="'Pretendard', monospace" font-size="14" font-weight="900" fill="{accent}" text-anchor="middle">{num_str}</text>
            </g>
            
            <!-- 카드 타이틀 -->
            <text x="32" y="105" font-family="'Pretendard', sans-serif" font-size="25" font-weight="900" fill="#ffffff">{item_title}</text>
            
            <!-- 구분선 (사이버 그라디언트) -->
            <line x1="32" y1="128" x2="{card_width - 32}" y2="128" stroke="#334155" stroke-width="2" />
            
            <!-- 내용 블록 리스트 -->
            <g transform="translate(32, 165)">
                <!-- 항목 1 -->
                <rect x="0" y="-12" width="6" height="32" rx="3" fill="{accent}" />
                <text x="18" y="10" font-family="'Pretendard', sans-serif" font-size="19" font-weight="600" fill="#f8fafc">{item_desc1}</text>
                
                <!-- 항목 2 -->
                <rect x="0" y="48" width="6" height="32" rx="3" fill="{accent}" />
                <text x="18" y="70" font-family="'Pretendard', sans-serif" font-size="19" font-weight="600" fill="#f8fafc">{item_desc2}</text>
                
                <!-- 항목 3 -->
                <rect x="0" y="108" width="6" height="32" rx="3" fill="{accent_sub}" />
                <text x="18" y="130" font-family="'Pretendard', sans-serif" font-size="19" font-weight="600" fill="#cbd5e1">{item_desc3}</text>
            </g>
            
            <!-- 하단 터미널 커맨드 / 하이라이트 박스 -->
            <g transform="translate(28, {card_height - 96})">
                <rect width="{card_width - 56}" height="64" rx="14" fill="#030712" stroke="{accent}" stroke-width="1.5" />
                <text x="24" y="38" font-family="'Pretendard', monospace" font-size="16" font-weight="700" fill="{accent}">$&gt; {highlight}</text>
            </g>
        </g>
        """

    svg = f"""<svg width="1536" height="1024" viewBox="0 0 1536 1024" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#090d16" />
      <stop offset="50%" stop-color="#0f172a" />
      <stop offset="100%" stop-color="#030712" />
    </linearGradient>

    <linearGradient id="cyberAccent" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="{accent}" />
      <stop offset="100%" stop-color="{accent_sub}" />
    </linearGradient>

    <filter id="glowFilter" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="40" result="blur" />
    </filter>

    <filter id="dropShadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="16" stdDeviation="20" flood-color="#000000" flood-opacity="0.7" />
    </filter>
  </defs>

  <!-- 메인 배경 -->
  <rect width="1536" height="1024" fill="url(#bgGrad)" />

  <!-- 사이버 그리드 배경 효과 -->
  <g opacity="0.05" stroke="#38bdf8" stroke-width="1">
    <line x1="0" y1="128" x2="1536" y2="128" /><line x1="0" y1="256" x2="1536" y2="256" />
    <line x1="0" y1="384" x2="1536" y2="384" /><line x1="0" y1="512" x2="1536" y2="512" />
    <line x1="0" y1="640" x2="1536" y2="640" /><line x1="0" y1="768" x2="1536" y2="768" />
    <line x1="256" y1="0" x2="256" y2="1024" /><line x1="512" y1="0" x2="512" y2="1024" />
    <line x1="768" y1="0" x2="768" y2="1024" /><line x1="1024" y1="0" x2="1024" y2="1024" />
    <line x1="1280" y1="0" x2="1280" y2="1024" />
  </g>

  <!-- 배경 앰비언트 글로우 -->
  <circle cx="150" cy="180" r="300" fill="{accent}" opacity="0.12" filter="url(#glowFilter)" />
  <circle cx="1380" cy="850" r="320" fill="{accent_sub}" opacity="0.1" filter="url(#glowFilter)" />

  <!-- 외곽 사이버 프레임 -->
  <rect x="40" y="40" width="1456" height="944" rx="28" fill="none" stroke="{accent}" stroke-opacity="0.3" stroke-width="2" />
  <rect x="52" y="52" width="1432" height="920" rx="20" fill="none" stroke="#ffffff" stroke-opacity="0.05" stroke-width="1" />

  <!-- 상단 브랜드 & 뱃지 영역 -->
  <g transform="translate(98, 90)">
    <rect width="46" height="46" rx="12" fill="url(#cyberAccent)" />
    <path d="M12 33 L23 13 L34 33 M16 26 L30 26" stroke="#090d16" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    <text x="62" y="32" font-family="'Pretendard', sans-serif" font-size="24" font-weight="900" fill="#ffffff">앱시안</text>
    <text x="145" y="32" font-family="'Pretendard', sans-serif" font-size="16" font-weight="700" fill="{accent}">absian</text>

    <!-- 분류 뱃지 -->
    <g transform="translate(270, 4)">
        <rect width="{len(badge_text) * 16 + 40}" height="40" rx="20" fill="#1e293b" stroke="{accent}" stroke-width="1.8" />
        <text x="20" y="26" font-family="'Pretendard', sans-serif" font-size="16" font-weight="800" fill="{accent}">⚡ {escape(badge_text)}</text>
    </g>
  </g>

  <!-- 메인 헤드라인 및 설명문 -->
  <g transform="translate(98, 190)">
    <text x="0" y="0" font-family="'Pretendard', sans-serif" font-size="44" font-weight="900" fill="#ffffff" letter-spacing="-1">{escape(clean_text(title, 34))}</text>
    <text x="0" y="46" font-family="'Pretendard', sans-serif" font-size="23" font-weight="500" fill="#94a3b8">{escape(clean_text(subtitle, 50))}</text>
  </g>

  <!-- 중앙 3개 카드 영역 -->
  {cards_svg}

  <!-- 하단 터미널 스타일 푸터 바 -->
  <g transform="translate(98, 880)">
    <rect width="1340" height="56" rx="16" fill="#090d16" stroke="#1e293b" stroke-width="2" />
    <circle cx="28" cy="28" r="6" fill="#10b981" />
    <text x="48" y="34" font-family="'Pretendard', sans-serif" font-size="17" font-weight="700" fill="#38bdf8">실무 검증 아키텍처 다이어그램</text>
    <text x="340" y="34" font-family="'Pretendard', sans-serif" font-size="16" font-weight="500" fill="#64748b">| Playwright, Celery, K8s, AIO 최적화 설계 완벽 반영</text>
    <text x="1310" y="34" font-family="'Pretendard', sans-serif" font-size="16" font-weight="600" fill="{accent}" text-anchor="end">absianp.github.io</text>
  </g>
</svg>"""
    return svg.strip()


def convert_svg_to_webp(svg_path: Path, webp_path: Path) -> bool:
    """ffmpeg를 이용해 1536x1024 고화질 WebP로 변환"""
    webp_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        cmd = [
            "/usr/bin/ffmpeg", "-y",
            "-i", str(svg_path),
            "-update", "1",
            "-frames:v", "1",
            "-vf", "scale=1536:1024",
            "-c:v", "libwebp",
            "-lossless", "0",
            "-q:v", "85",
            str(webp_path)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return res.returncode == 0 and webp_path.exists()
    except Exception as e:
        print(f"⚠️ [article_image_generator] ffmpeg 변환 실패: {e}")
        return False


def build_figure_block(asset_key: str, relative_url: str, alt: str, caption: str) -> str:
    """Astro 표준 figure 마크다운 블록 생성"""
    return (
        f"<!-- article-illustration:{asset_key} -->\n"
        f'<figure class="article-illustration" style="margin: 2em 0;">\n'
        f'  <img src="{escape(relative_url, quote=True)}" alt="{escape(alt, quote=True)}" '
        f'width="1536" height="1024" loading="lazy" decoding="async" '
        f'style="display: block; width: 100%; max-width: 100%; height: auto; border-radius: 0.75rem;" />\n'
        f'  <figcaption style="margin-top: 0.65em; font-size: 0.95em; line-height: 1.6; color: #475569;">'
        f'{escape(caption, quote=True)}</figcaption>\n'
        f'</figure>\n'
        f'<!-- /article-illustration:{asset_key} -->'
    )


def generate_and_integrate_article_images(
    article: Dict[str, Any],
    slug: str,
    output_dir: Optional[Path] = None,
    site_prefix: str = SITE_PREFIX
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    글 본문(markdown_content)에 설명 이해용 이미지 2개를 생성하고 적절한 H2 앞에 자동 삽입.
    반환: (수정된 markdown_content, 생성된 이미지 메타데이터 목록)
    """
    content = article.get("markdown_content", "")
    title = article.get("title", "")
    category = article.get("category", "개발 & 테크")

    out_dir = Path(output_dir) if output_dir else PUBLIC_IMG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # 이미 삽입된 article-illustration이 2개 이상 있으면 중복 생성하지 않고 메타데이터만 반환
    existing_figures = re.findall(r"<!-- article-illustration:([A-Za-z0-9_.-]+) -->", content)
    if len(existing_figures) >= 2:
        return content, [
            {"relative_url": f"/images/articles/{f}.webp", "asset_key": f} for f in existing_figures
        ]

    # 본문의 H2 섹션 분석
    sections = extract_h2_sections(content)
    h2_count = len(sections)

    # 이미지 1 기획: 첫 번째 또는 두 번째 H2
    sec1_title = sections[0][0].replace("## ", "") if sections else "주요 기술 아키텍처"
    sec1_body = sections[0][1] if sections else title
    img1_title = f"{sec1_title} 핵심 구조"
    img1_sub = "실무 워크플로우 및 데이터 파이프라인 개념도"
    img1_items = [
        {"title": "환경 설정 & 의존성", "desc1": "런타임 패키지 및 드라이버", "desc2": "격리된 실행 컨테이너 환경", "desc3": "리소스 제한 및 권한 격리", "highlight": "안정적인 실행 기반"},
        {"title": "핵심 로직 & 데이터 처리", "desc1": "동적 비동기 이벤트 핸들링", "desc2": "데이터 파싱 및 스키마 검증", "desc3": "예외 핸들링 및 재시도 전략", "highlight": "무중단 파이프라인"},
        {"title": "배포 & 파이프라인 연동", "desc1": "CI/CD 자동 빌드 및 테스트", "desc2": "실시간 로깅 및 성능 모니터링", "desc3": "결과물 원격 저장소 동기화", "highlight": "완전자동화 완료"}
    ]

    # 이미지 2 기획: 뒤쪽 H2
    sec2_idx = max(1, min(h2_count - 1, 2)) if h2_count > 1 else 0
    sec2_title = sections[sec2_idx][0].replace("## ", "") if sections else "실전 적용 및 최적화 전략"
    sec2_body = sections[sec2_idx][1] if sections else "성능 극대화 팁"
    img2_title = f"{sec2_title} 최적화 가이드"
    img2_sub = "프로덕션 환경에서 놓치지 말아야 할 성능 및 보안 체크포인트"
    img2_items = [
        {"title": "성능 최적화 튜닝", "desc1": "비동기 I/O 및 캐싱 적용", "desc2": "메모리 누수 방지 리소스 회수", "desc3": "요청 레이턴시 대폭 단축", "highlight": "처리 속도 극대화"},
        {"title": "보안 & 정책 준수", "desc1": "민감 정보 환경변수 분리", "desc2": "Rate Limit 및 차단 우회", "desc3": "검색 엔진 크롤링 정책 준수", "highlight": "안전한 상용 운영"},
        {"title": "유지보수 & 확장성", "desc1": "구조화된 로그 수집 및 추적", "desc2": "에러 발생 시 즉각 알림 전송", "desc3": "스케일아웃 확장 설계", "highlight": "견고한 아키텍처"}
    ]

    # 이미지 파일 생성
    key1 = f"{site_prefix}-{slug}-01"
    key2 = f"{site_prefix}-{slug}-02"

    svg1 = generate_tech_infographic_svg(img1_title, img1_sub, "architecture", category, img1_items)
    svg2 = generate_tech_infographic_svg(img2_title, img2_sub, "workflow", category, img2_items)

    tmp_dir = Path("/tmp")
    svg1_path = tmp_dir / f"{key1}.svg"
    svg2_path = tmp_dir / f"{key2}.svg"
    svg1_path.write_text(svg1, encoding="utf-8")
    svg2_path.write_text(svg2, encoding="utf-8")

    webp1_path = out_dir / f"{key1}.webp"
    webp2_path = out_dir / f"{key2}.webp"

    convert_svg_to_webp(svg1_path, webp1_path)
    convert_svg_to_webp(svg2_path, webp2_path)

    # dist 폴더에도 동기화 복사
    try:
        DIST_IMG_DIR.mkdir(parents=True, exist_ok=True)
        if webp1_path.exists():
            DIST_IMG_DIR.joinpath(f"{key1}.webp").write_bytes(webp1_path.read_bytes())
        if webp2_path.exists():
            DIST_IMG_DIR.joinpath(f"{key2}.webp").write_bytes(webp2_path.read_bytes())
    except Exception:
        pass

    # 본문 삽입 위치 결정
    alt1 = f"{title} - {sec1_title} 설명 다이어그램"
    cap1 = f"{sec1_title}의 핵심 구조와 워크플로우를 정리한 다이어그램입니다. AI로 제작한 설명용 이미지입니다."
    fig1 = build_figure_block(key1, f"/images/articles/{key1}.webp", alt1, cap1)

    alt2 = f"{title} - {sec2_title} 실전 가이드 다이어그램"
    cap2 = f"{sec2_title}의 주요 구현 단계와 최적화 포인트를 정리한 다이어그램입니다. AI로 제작한 설명용 이미지입니다."
    fig2 = build_figure_block(key2, f"/images/articles/{key2}.webp", alt2, cap2)

    updated_content = content
    # H2가 있으면 해당 H2 앞에 삽입
    if sections:
        target_h2_1 = sections[0][0]
        if target_h2_1 in updated_content:
            updated_content = updated_content.replace(target_h2_1, f"{fig1}\n\n{target_h2_1}", 1)

        if h2_count > 1:
            target_h2_2 = sections[sec2_idx][0]
            if target_h2_2 in updated_content:
                updated_content = updated_content.replace(target_h2_2, f"{fig2}\n\n{target_h2_2}", 1)
        else:
            updated_content += f"\n\n{fig2}\n"
    else:
        updated_content = f"{fig1}\n\n{updated_content}\n\n{fig2}\n"

    images_meta = [
        {
            "asset_key": key1,
            "relative_url": f"/images/articles/{key1}.webp",
            "file_path": str(webp1_path),
            "alt": alt1,
            "caption": cap1
        },
        {
            "asset_key": key2,
            "relative_url": f"/images/articles/{key2}.webp",
            "file_path": str(webp2_path),
            "alt": alt2,
            "caption": cap2
        }
    ]

    return updated_content, images_meta
