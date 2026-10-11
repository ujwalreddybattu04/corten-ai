"""
Report Generation Service — Corten AI's professional report engine.

Pipeline:
1. RESEARCH: Deep web search across multiple sources (reuses existing tools)
2. OUTLINE: LLM generates structured report outline (JSON)
3. WRITE: LLM writes each section with citations, streamed via SSE
4. FORMAT: ReportLab generates a branded PDF
5. DELIVER: Temp file stored, download URL returned

Streams SSE events to the frontend for a Claude-like live progress UI.
"""

import json
import os
import uuid
import asyncio
import logging
import time
import re
from datetime import datetime
from typing import AsyncGenerator, Dict, Any, List

from src.config.settings import settings
from src.config.prompts import (
    REPORT_OUTLINE_PROMPT,
    REPORT_SECTION_PROMPT,
    REPORT_EXECUTIVE_SUMMARY_PROMPT,
)

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
MAX_SOURCES_PER_SEARCH = 6
MAX_TOTAL_SOURCES = 20
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "reports")

# Ensure reports directory exists
os.makedirs(REPORTS_DIR, exist_ok=True)


class ReportService:
    """
    Generates professional PDF reports with live progress streaming.
    Follows the Claude pattern: research → plan → write → format → deliver.
    """

    async def stream_report(
        self, topic: str, focus_mode: str = "all"
    ) -> AsyncGenerator[str, None]:
        """
        Main entry point. Streams SSE events showing live report generation progress.

        Events emitted:
        - report_start: {topic, report_id}
        - report_status: {content}
        - research_step: {step, detail}
        - sources: {sources, items}
        - report_outline: {title, subtitle, sections}
        - section_start: {index, title, total}
        - section_content: {index, chunk}
        - section_complete: {index, title}
        - report_generating_pdf: {step}
        - report_complete: {download_url, filename, pages, title}
        - error: {message}
        - done: {}
        """
        from src.services.web_search_service import tavily_search_service
        from src.services.llm_service import groq_llm_service
        from src.config.prompts import FOCUS_MODE_SEARCH_MODIFIERS

        report_id = str(uuid.uuid4())[:12]
        start_time = time.time()

        try:
            yield _sse("report_start", {"topic": topic, "report_id": report_id})

            # ── PHASE 1: DEEP RESEARCH ────────────────────────────────────
            yield _sse("report_status", {"content": "Researching topic across multiple sources..."})

            # Generate research sub-queries
            yield _sse("research_step", {"step": "Planning", "detail": "Identifying key research angles"})

            plan = await self._generate_research_plan(groq_llm_service, topic)
            sub_queries = plan.get("queries", [topic])

            # Apply focus mode modifier
            search_modifier = ""
            if focus_mode and focus_mode != "all":
                search_modifier = FOCUS_MODE_SEARCH_MODIFIERS.get(focus_mode, "")

            # Search all sub-queries in parallel
            all_sources: List[Dict[str, Any]] = []
            seen_urls: set = set()

            for sq in sub_queries:
                yield _sse("research_step", {"step": "Searching", "detail": sq})

            search_query_list = [
                f"{sq} {search_modifier}".strip() if search_modifier else sq
                for sq in sub_queries
            ]

            search_tasks = [
                tavily_search_service.search(sq, max_results=MAX_SOURCES_PER_SEARCH)
                for sq in search_query_list
            ]

            results = await asyncio.gather(*search_tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.warning(f"[ReportService] Search failed: {result}")
                    continue
                if not isinstance(result, dict):
                    continue
                for item in result.get("results", []):
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_sources.append(item)
                    if len(all_sources) >= MAX_TOTAL_SOURCES:
                        break
                if len(all_sources) >= MAX_TOTAL_SOURCES:
                    break

            yield _sse("research_step", {
                "step": "Reading",
                "detail": f"Analyzing {len(all_sources)} sources",
            })

            # Format and send sources to frontend
            frontend_sources = self._format_sources(all_sources)
            yield _sse("sources", {"sources": frontend_sources, "items": frontend_sources})

            research_time = time.time() - start_time
            yield _sse("report_status", {
                "content": f"Research complete — {len(all_sources)} sources gathered in {research_time:.1f}s",
            })

            # ── PHASE 2: REPORT OUTLINE ───────────────────────────────────
            yield _sse("report_status", {"content": "Planning report structure..."})
            yield _sse("research_step", {"step": "Planning", "detail": "Generating professional report outline"})

            outline = await self._generate_outline(groq_llm_service, topic, all_sources)

            report_title = outline.get("title", f"Report: {topic}")
            report_subtitle = outline.get("subtitle", "")
            sections = outline.get("sections", [])

            if not sections:
                sections = [
                    {"title": "Overview", "description": f"Overview of {topic}", "key_points": []},
                    {"title": "Key Findings", "description": f"Major findings about {topic}", "key_points": []},
                    {"title": "Analysis", "description": f"Detailed analysis of {topic}", "key_points": []},
                    {"title": "Conclusion", "description": f"Conclusions and outlook", "key_points": []},
                ]

            yield _sse("report_outline", {
                "title": report_title,
                "subtitle": report_subtitle,
                "sections": [{"title": s["title"], "description": s.get("description", "")} for s in sections],
            })

            yield _sse("report_status", {
                "content": f"Report structure ready — {len(sections)} sections planned",
            })

            # ── PHASE 3: WRITE EACH SECTION ───────────────────────────────
            written_sections: List[Dict[str, str]] = []
            total_sections = len(sections)

            # Write executive summary first
            yield _sse("section_start", {"index": 0, "title": "Executive Summary", "total": total_sections + 1})
            yield _sse("report_status", {"content": "Writing Executive Summary..."})

            exec_summary = await self._write_executive_summary(
                groq_llm_service, report_title, sections, all_sources
            )
            written_sections.append({"title": "Executive Summary", "content": exec_summary})

            yield _sse("section_content", {"index": 0, "chunk": exec_summary})
            yield _sse("section_complete", {"index": 0, "title": "Executive Summary"})

            # Write each body section
            for idx, section in enumerate(sections):
                section_num = idx + 1
                yield _sse("section_start", {
                    "index": section_num,
                    "title": section["title"],
                    "total": total_sections + 1,
                })
                yield _sse("report_status", {
                    "content": f"Writing section {section_num}/{total_sections}: {section['title']}",
                })

                section_content = await self._write_section(
                    groq_llm_service, report_title, section, all_sources
                )
                written_sections.append({"title": section["title"], "content": section_content})

                yield _sse("section_content", {"index": section_num, "chunk": section_content})
                yield _sse("section_complete", {"index": section_num, "title": section["title"]})

            # ── PHASE 4: GENERATE PDF ─────────────────────────────────────
            yield _sse("report_status", {"content": "Formatting professional PDF..."})
            yield _sse("report_generating_pdf", {"step": "Building cover page"})

            filename = f"corten_report_{report_id}.pdf"
            filepath = os.path.join(REPORTS_DIR, filename)

            yield _sse("report_generating_pdf", {"step": "Adding sections and citations"})

            pages = self._generate_pdf(
                filepath=filepath,
                title=report_title,
                subtitle=report_subtitle,
                sections=written_sections,
                sources=all_sources,
                topic=topic,
            )

            yield _sse("report_generating_pdf", {"step": "Finalizing document"})

            # ── PHASE 5: DELIVER ──────────────────────────────────────────
            file_size = os.path.getsize(filepath)
            total_time = time.time() - start_time

            yield _sse("report_complete", {
                "download_url": f"/api/v1/report/download/{report_id}",
                "filename": filename,
                "pages": pages,
                "title": report_title,
                "subtitle": report_subtitle,
                "file_size": file_size,
                "sources_count": len(all_sources),
                "generation_time": round(total_time, 1),
            })

            yield _sse("done", {})

        except Exception as e:
            logger.exception(f"[ReportService] Report generation failed: {e}")
            error_msg = str(e)
            if "Tavily" in error_msg or "usage limit" in error_msg.lower():
                error_msg = "Web search limit reached. Please check your search provider plan."
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                error_msg = "API rate limit reached. Please wait a moment."
            yield _sse("error", {"message": error_msg})
            yield _sse("done", {})

    # ── Internal Methods ──────────────────────────────────────────────────────

    async def _generate_research_plan(self, llm_service, topic: str) -> Dict[str, Any]:
        """Generate research sub-queries for the report topic."""
        prompt = (
            "You are a research strategist. Generate 3-5 specific search queries "
            "to comprehensively research this topic for a professional report.\n\n"
            "Output JSON:\n"
            '{"queries": ["query1", "query2", ...]}\n\n'
            "Make queries specific, diverse, and optimized for web search."
        )
        try:
            response = await llm_service.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Topic: {topic}"},
                ],
                model=settings.ROUTER_MODEL,
                temperature=0.3,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"[ReportService] Research plan failed: {e}")
            return {"queries": [topic, f"{topic} latest developments", f"{topic} analysis"]}

    async def _generate_outline(
        self, llm_service, topic: str, sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate a structured report outline from the topic and sources."""
        source_summary = "\n".join(
            f"- {s.get('title', 'N/A')}: {s.get('snippet', '')[:200]}"
            for s in sources[:10]
        )

        try:
            response = await llm_service.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": REPORT_OUTLINE_PROMPT},
                    {"role": "user", "content": f"TOPIC: {topic}\n\nAVAILABLE SOURCES:\n{source_summary}"},
                ],
                model=settings.DEFAULT_MODEL,
                temperature=0.3,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"[ReportService] Outline generation failed: {e}")
            return {
                "title": f"{topic}: A Comprehensive Analysis",
                "subtitle": f"Research Report — {datetime.now().strftime('%B %Y')}",
                "sections": [],
            }

    async def _write_executive_summary(
        self, llm_service, report_title: str, sections: list, sources: list
    ) -> str:
        """Write the executive summary."""
        section_titles = ", ".join(s["title"] for s in sections)
        prompt = REPORT_EXECUTIVE_SUMMARY_PROMPT.format(
            report_title=report_title,
            section_titles=section_titles,
        )
        # Add sources
        for idx, src in enumerate(sources[:8], 1):
            snippet = src.get("snippet", "")[:300]
            prompt += f"Source [{idx}]: {src.get('title', 'N/A')}\n{snippet}\n\n"

        try:
            response = await llm_service.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Write the executive summary for: {report_title}"},
                ],
                model=settings.DEFAULT_MODEL,
                temperature=0.3,
                max_tokens=1024,
            )
            return self._clean_section(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"[ReportService] Executive summary failed: {e}")
            return f"This report provides a comprehensive analysis of {report_title}."

    async def _write_section(
        self, llm_service, report_title: str, section: Dict, sources: list
    ) -> str:
        """Write a single report section with citations."""
        current_date = datetime.now().strftime("%B %d, %Y")
        key_points = ", ".join(section.get("key_points", [])) or "Cover all relevant aspects"

        prompt = REPORT_SECTION_PROMPT.format(
            brand_name=settings.BRAND_NAME,
            current_date=current_date,
            report_title=report_title,
            section_title=section["title"],
            section_description=section.get("description", ""),
            key_points=key_points,
        )
        # Add sources to context
        for idx, src in enumerate(sources[:8], 1):
            snippet = src.get("snippet", "")[:400]
            prompt += f"Source [{idx}]: {src.get('title', 'N/A')}\n{snippet}\n\n"

        try:
            response = await llm_service.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Write the '{section['title']}' section."},
                ],
                model=settings.DEFAULT_MODEL,
                temperature=0.3,
                max_tokens=2048,
            )
            return self._clean_section(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"[ReportService] Section write failed: {e}")
            return f"Content for {section['title']} could not be generated."

    def _clean_section(self, text: str) -> str:
        """Remove any source/reference lists the LLM might have added."""
        cutoff = re.compile(
            r'(?:\n+)\s*(?:(?:\*\*|### ?|# ?)?(?:Sources|References|Bibliography|Works Cited)(?:\*\*|:)?)',
            re.IGNORECASE,
        )
        match = cutoff.search(text)
        if match:
            text = text[:match.start()]
        return text.strip()

    def _format_sources(self, sources: list) -> list:
        """Format sources for frontend display."""
        formatted = []
        for idx, src in enumerate(sources, 1):
            domain = src.get("domain", "website")
            formatted.append({
                "url": src.get("url", ""),
                "title": src.get("title", "Source"),
                "domain": domain,
                "favicon": f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
                "snippet": src.get("snippet", ""),
                "citationIndex": idx,
            })
        return formatted

    # ── PDF Generation ────────────────────────────────────────────────────────

    def _generate_pdf(
        self,
        filepath: str,
        title: str,
        subtitle: str,
        sections: List[Dict[str, str]],
        sources: List[Dict[str, Any]],
        topic: str,
    ) -> int:
        """
        Generate a professionally formatted PDF using ReportLab.
        Returns the number of pages.
        """
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.colors import HexColor
        from reportlab.lib.units import inch, mm
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, PageBreak,
            Table, TableStyle, HRFlowable,
        )

        # ── Document Setup ────────────────────────────────────────────
        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            topMargin=30 * mm,
            bottomMargin=25 * mm,
            leftMargin=25 * mm,
            rightMargin=25 * mm,
            title=title,
            author=f"{settings.BRAND_NAME} by {settings.COMPANY_NAME}",
        )

        # ── Styles ────────────────────────────────────────────────────
        styles = getSampleStyleSheet()

        brand_color = HexColor("#2563EB")
        dark_color = HexColor("#1a1a2e")
        text_color = HexColor("#333333")
        muted_color = HexColor("#666666")

        styles.add(ParagraphStyle(
            name="CoverTitle",
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=34,
            textColor=dark_color,
            alignment=TA_LEFT,
            spaceAfter=12,
        ))
        styles.add(ParagraphStyle(
            name="CoverSubtitle",
            fontName="Helvetica",
            fontSize=14,
            leading=18,
            textColor=muted_color,
            alignment=TA_LEFT,
            spaceAfter=8,
        ))
        styles.add(ParagraphStyle(
            name="CoverMeta",
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=muted_color,
            alignment=TA_LEFT,
        ))
        styles.add(ParagraphStyle(
            name="SectionTitle",
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=dark_color,
            spaceBefore=24,
            spaceAfter=12,
        ))
        styles.add(ParagraphStyle(
            name="SubsectionTitle",
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=dark_color,
            spaceBefore=16,
            spaceAfter=8,
        ))
        styles.add(ParagraphStyle(
            name="BodyText2",
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            textColor=text_color,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        ))
        styles.add(ParagraphStyle(
            name="Citation",
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=muted_color,
            spaceAfter=4,
        ))
        styles.add(ParagraphStyle(
            name="Footer",
            fontName="Helvetica",
            fontSize=8,
            textColor=muted_color,
            alignment=TA_CENTER,
        ))

        # ── Build Document Content ────────────────────────────────────
        story = []

        # Cover Page
        story.append(Spacer(1, 80))

        # Brand line
        story.append(Paragraph(
            f'<font color="#{brand_color.hexval()[2:]}">{settings.BRAND_NAME.upper()}</font>'
            f'<font color="#999999"> — AI Research Report</font>',
            ParagraphStyle(
                name="BrandLine",
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=14,
                textColor=brand_color,
                spaceAfter=24,
            ),
        ))

        # Accent line
        story.append(HRFlowable(
            width="30%", thickness=3, color=brand_color,
            spaceAfter=20, hAlign="LEFT",
        ))

        story.append(Paragraph(title, styles["CoverTitle"]))

        if subtitle:
            story.append(Paragraph(subtitle, styles["CoverSubtitle"]))

        story.append(Spacer(1, 40))

        # Meta information
        current_date = datetime.now().strftime("%B %d, %Y")
        meta_lines = [
            f"<b>Date:</b> {current_date}",
            f"<b>Sources:</b> {len(sources)} research sources analyzed",
            f"<b>Generated by:</b> {settings.BRAND_NAME} AI by {settings.COMPANY_NAME}",
        ]
        for line in meta_lines:
            story.append(Paragraph(line, styles["CoverMeta"]))
            story.append(Spacer(1, 4))

        story.append(PageBreak())

        # Table of Contents
        story.append(Paragraph("Table of Contents", styles["SectionTitle"]))
        story.append(Spacer(1, 8))

        toc_data = []
        for idx, section in enumerate(sections):
            toc_data.append([
                Paragraph(f"{idx + 1}.", ParagraphStyle(
                    name=f"TOCNum{idx}", fontName="Helvetica-Bold",
                    fontSize=10.5, textColor=brand_color,
                )),
                Paragraph(section["title"], ParagraphStyle(
                    name=f"TOCTitle{idx}", fontName="Helvetica",
                    fontSize=10.5, textColor=text_color,
                )),
            ])

        if toc_data:
            toc_table = Table(toc_data, colWidths=[30, 400])
            toc_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (0, -1), 0),
            ]))
            story.append(toc_table)

        story.append(PageBreak())

        # Sections
        for idx, section in enumerate(sections):
            # Section header
            section_num = idx + 1
            story.append(Paragraph(
                f'<font color="#{brand_color.hexval()[2:]}">{section_num}.</font> {section["title"]}',
                styles["SectionTitle"],
            ))

            story.append(HRFlowable(
                width="100%", thickness=0.5, color=HexColor("#E0E0E0"),
                spaceAfter=12,
            ))

            # Section content — parse markdown into paragraphs
            content = section.get("content", "")
            paragraphs = self._markdown_to_paragraphs(content, styles)
            for p in paragraphs:
                story.append(p)

            story.append(Spacer(1, 12))

        # References Page
        story.append(PageBreak())
        story.append(Paragraph("References", styles["SectionTitle"]))
        story.append(HRFlowable(
            width="100%", thickness=0.5, color=HexColor("#E0E0E0"),
            spaceAfter=12,
        ))

        for idx, src in enumerate(sources[:15], 1):
            title_text = src.get("title", "Untitled")
            url = src.get("url", "")
            domain = src.get("domain", "")
            ref_text = f"[{idx}] <b>{title_text}</b>"
            if domain:
                ref_text += f" — {domain}"
            if url:
                ref_text += f'<br/><font color="#{brand_color.hexval()[2:]}">{url[:80]}{"..." if len(url) > 80 else ""}</font>'
            story.append(Paragraph(ref_text, styles["Citation"]))
            story.append(Spacer(1, 4))

        # Build with page numbers
        def add_page_number(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(HexColor("#999999"))
            page_num = canvas.getPageNumber()
            text = f"{settings.BRAND_NAME} AI Report  •  Page {page_num}"
            canvas.drawCentredString(A4[0] / 2, 15 * mm, text)
            canvas.restoreState()

        doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)

        # Count pages
        from reportlab.lib.pagesizes import A4 as _A4
        try:
            from reportlab.pdfbase.pdfmetrics import stringWidth
            # Simple page count by reopening
            import io
            with open(filepath, "rb") as f:
                content = f.read()
            # Count page markers in PDF
            pages = content.count(b"/Type /Page") - content.count(b"/Type /Pages")
            return max(pages, 1)
        except Exception:
            return len(sections) + 3  # estimate

    def _markdown_to_paragraphs(self, text: str, styles) -> list:
        """Convert markdown text to ReportLab paragraph objects."""
        from reportlab.platypus import Paragraph, Spacer

        elements = []
        lines = text.split("\n")
        current_para = []

        for line in lines:
            stripped = line.strip()

            if not stripped:
                # Flush current paragraph
                if current_para:
                    para_text = " ".join(current_para)
                    para_text = self._md_inline(para_text)
                    elements.append(Paragraph(para_text, styles["BodyText2"]))
                    current_para = []
                continue

            if stripped.startswith("### "):
                # Flush first
                if current_para:
                    para_text = " ".join(current_para)
                    para_text = self._md_inline(para_text)
                    elements.append(Paragraph(para_text, styles["BodyText2"]))
                    current_para = []
                heading = stripped[4:].strip()
                heading = self._md_inline(heading)
                elements.append(Paragraph(heading, styles["SubsectionTitle"]))
                continue

            if stripped.startswith("## "):
                if current_para:
                    para_text = " ".join(current_para)
                    para_text = self._md_inline(para_text)
                    elements.append(Paragraph(para_text, styles["BodyText2"]))
                    current_para = []
                heading = stripped[3:].strip()
                heading = self._md_inline(heading)
                elements.append(Paragraph(heading, styles["SubsectionTitle"]))
                continue

            if stripped.startswith("- ") or stripped.startswith("* "):
                if current_para:
                    para_text = " ".join(current_para)
                    para_text = self._md_inline(para_text)
                    elements.append(Paragraph(para_text, styles["BodyText2"]))
                    current_para = []
                bullet_text = stripped[2:].strip()
                bullet_text = self._md_inline(bullet_text)
                elements.append(Paragraph(
                    f"•  {bullet_text}", styles["BodyText2"]
                ))
                continue

            current_para.append(stripped)

        # Flush remaining
        if current_para:
            para_text = " ".join(current_para)
            para_text = self._md_inline(para_text)
            elements.append(Paragraph(para_text, styles["BodyText2"]))

        return elements

    def _md_inline(self, text: str) -> str:
        """Convert inline markdown (bold, italic, citations) to ReportLab XML."""
        # Bold: **text** → <b>text</b>
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        # Italic: *text* → <i>text</i>
        text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
        # Citations: [1] → <super>[1]</super>
        text = re.sub(r'\[(\d+)\]', r'<super>[\1]</super>', text)
        # Clean any remaining markdown artifacts
        text = text.replace("&", "&amp;").replace("<b>", "§B§").replace("</b>", "§/B§")
        text = text.replace("<i>", "§I§").replace("</i>", "§/I§")
        text = text.replace("<super>", "§S§").replace("</super>", "§/S§")
        text = text.replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace("§B§", "<b>").replace("§/B§", "</b>")
        text = text.replace("§I§", "<i>").replace("§/I§", "</i>")
        text = text.replace("§S§", "<super>").replace("§/S§", "</super>")
        return text

    def get_report_path(self, report_id: str) -> str | None:
        """Get the file path for a generated report."""
        filename = f"corten_report_{report_id}.pdf"
        filepath = os.path.join(REPORTS_DIR, filename)
        if os.path.exists(filepath):
            return filepath
        return None


# ── Helper ────────────────────────────────────────────────────────────────────

def _sse(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


report_service = ReportService()
