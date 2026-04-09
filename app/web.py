# app/web.py — браузерный просмотр статей из БД
from __future__ import annotations

from datetime import date, datetime, time, timezone, timedelta
import html
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from flask import Flask, redirect, render_template_string, request
from sqlalchemy import func, inspect, select

from app.config import settings
from app.db import SessionLocal
from app.digest import (
    EVENT_BADGE,
    TAG_ORDER,
    TAG_TITLES,
    _build_digest_topics,
    _article_tags,
    _best_summary,
    _render_title,
    get_articles_for_digest,
)
from app.models import Article, ArticleReview, DigestRun
from app.pipeline import _resolve_digest_window, retry_digest_run

app = Flask(__name__)

LOCAL_TZ = ZoneInfo(settings.digest_tz)

PAGE_SIZE = 50
EVENT_TYPE_OPTIONS = ["LAW_DRAFT", "LAW_ADOPTED", "GUIDANCE", "ENFORCEMENT", "COURTS", "MARKET_CASES"]
TAG_OPTIONS = [
    "pdn",
    "advertising",
    "competition",
    "banking",
    "telecom",
    "it_platforms",
    "cybersecurity",
    "ip",
    "consumers",
    "_other",
]

TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Legal Digest — рабочая панель</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {
  --bg: #f4f1ea;
  --surface: rgba(255, 252, 246, 0.86);
  --surface-strong: rgba(255, 255, 255, 0.94);
  --ink: #18211c;
  --muted: #647066;
  --line: rgba(24, 33, 28, 0.1);
  --primary: #1f5d4a;
  --primary-strong: #123d31;
  --accent: #d9c37a;
  --accent-soft: #f3ecd2;
  --danger: #a04836;
  --warn: #9c6c1f;
  --shadow: 0 22px 52px rgba(42, 44, 31, 0.12);
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  min-height: 100vh;
  color: var(--ink);
  font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
  background:
    radial-gradient(circle at top left, rgba(217, 195, 122, 0.42), transparent 28%),
    radial-gradient(circle at top right, rgba(31, 93, 74, 0.12), transparent 22%),
    linear-gradient(180deg, #faf7f1 0%, var(--bg) 100%);
}
a { color: inherit; }
.page {
  max-width: 1500px;
  margin: 0 auto;
  padding: 26px 22px 42px;
}
.filters-shell, .workspace, .article, .digest-preview {
  background: var(--surface);
  backdrop-filter: blur(18px);
  border: 1px solid rgba(255, 255, 255, 0.72);
  box-shadow: var(--shadow);
  border-radius: 28px;
}
.topline {
  margin-bottom: 18px;
}
.topline h1 {
  margin: 0 0 6px;
  font-size: 24px;
}
.topline p {
  margin: 0;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.5;
}
.filters-shell {
  padding: 18px;
  margin-bottom: 18px;
}
.filters-shell details {
  border-top: 1px solid rgba(24, 33, 28, 0.08);
  padding-top: 14px;
}
.filters-shell summary {
  cursor: pointer;
  list-style: none;
  font-size: 14px;
  font-weight: 700;
}
.filters-shell summary::-webkit-details-marker {
  display: none;
}
.section-head {
  margin-bottom: 14px;
}
.section-head h2 {
  margin: 0;
  font-size: 20px;
}
.section-head p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.active-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 999px;
  background: rgba(217, 195, 122, 0.24);
  color: #6b5310;
  font-size: 13px;
  font-weight: 700;
}
.filter-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
}
.top-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 18px;
}
.pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 38px;
  padding: 0 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--line);
  text-decoration: none;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
}
.pill.active {
  background: linear-gradient(135deg, var(--primary), var(--primary-strong));
  border-color: transparent;
  color: #fff;
}
.pill.neutral-active {
  background: rgba(24, 33, 28, 0.08);
  color: var(--ink);
}
.filters-grid {
  display: grid;
  grid-template-columns: 1.5fr repeat(5, minmax(0, 1fr)) auto;
  gap: 10px;
  align-items: end;
}
.field {
  display: grid;
  gap: 6px;
}
.field label {
  font-size: 12px;
  color: var(--muted);
}
.field input, .field select {
  width: 100%;
  height: 46px;
  border-radius: 15px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.88);
  padding: 0 12px;
  color: var(--ink);
  font-size: 13px;
}
.checkbox-card {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 46px;
  padding: 0 12px;
  border-radius: 15px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.88);
  color: var(--muted);
  font-size: 13px;
}
.filter-actions {
  display: flex;
  gap: 8px;
}
.btn, .btn-soft, .btn-ghost {
  border: none;
  border-radius: 15px;
  min-height: 46px;
  padding: 0 16px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn {
  background: linear-gradient(135deg, var(--primary), var(--primary-strong));
  color: #fff;
}
.btn-soft {
  background: rgba(24, 33, 28, 0.06);
  color: var(--ink);
}
.btn-ghost {
  min-height: 38px;
  padding: 0 12px;
  background: rgba(24, 33, 28, 0.06);
  color: var(--ink);
}
.workspace {
  padding: 18px;
  margin-bottom: 18px;
}
.workspace.archive-workspace {
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 0;
}
.workspace-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.workspace-grid.secondary {
  grid-template-columns: 1.1fr .9fr;
}
.workspace-grid.single {
  grid-template-columns: 1fr;
}
.panel {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  box-shadow: none;
}
.panel h3 {
  margin: 0 0 6px;
  font-size: 18px;
}
.panel-meta {
  color: var(--muted);
  font-size: 13px;
  margin-bottom: 14px;
}
.metric-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.metric {
  padding: 12px;
  border-radius: 16px;
  background: rgba(24, 33, 28, 0.04);
  border: 1px solid rgba(24, 33, 28, 0.08);
}
.metric-label {
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 6px;
}
.metric-value {
  font-size: 20px;
  font-weight: 700;
}
.attention-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.attention-item {
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(252, 250, 246, 0.92);
  border: 1px solid rgba(24, 33, 28, 0.08);
}
.run-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 12px;
}
.run-status.sent { background: rgba(31, 93, 74, 0.12); color: var(--primary); }
.run-status.failed { background: rgba(160, 72, 54, 0.12); color: var(--danger); }
.run-status.built, .run-status.empty { background: rgba(217, 195, 122, 0.24); color: #7a5a11; }
.run-history {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.run-item {
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(252, 250, 246, 0.92);
  border: 1px solid rgba(24, 33, 28, 0.08);
}
.run-item.failed {
  border-color: rgba(160, 72, 54, 0.22);
}
.run-item.sent {
  border-color: rgba(31, 93, 74, 0.18);
}
.run-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}
.run-actions {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}
.run-error {
  margin-top: 8px;
  color: var(--danger);
  font-size: 12px;
  line-height: 1.45;
}
.preview-list, .digest-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.review-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}
.review-item {
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(252, 250, 246, 0.92);
  border: 1px solid rgba(24, 33, 28, 0.08);
}
.review-item strong {
  display: block;
  margin-bottom: 4px;
}
.preview-item, .digest-item {
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(252, 250, 246, 0.92);
  border: 1px solid rgba(24, 33, 28, 0.08);
}
.preview-item a, .digest-item a {
  text-decoration: none;
  font-weight: 600;
}
.preview-item a:hover, .digest-item a:hover { text-decoration: underline; }
.subline {
  margin-top: 6px;
  color: var(--muted);
  font-size: 12px;
}
.digest-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}
.digest-main {
  min-width: 0;
}
.digest-count {
  flex: 0 0 auto;
  padding: 8px 11px;
  border-radius: 999px;
  background: rgba(31, 93, 74, 0.08);
  color: var(--primary-strong);
  font-size: 12px;
  font-weight: 700;
}
.digest-item.active {
  border-color: rgba(31, 93, 74, 0.24);
  background: rgba(232, 243, 238, 0.88);
}
.empty {
  padding: 16px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.58);
  color: var(--muted);
  font-size: 13px;
}
.feed {
  display: grid;
  gap: 16px;
}
.digest-preview {
  padding: 18px;
  margin-bottom: 18px;
}
.digest-preview h3 {
  margin: 0 0 6px;
  font-size: 18px;
}
.telegram-mock {
  background: linear-gradient(180deg, #e9f2ea 0%, #dbe8dc 100%);
  border: 1px solid rgba(24, 33, 28, 0.08);
  border-radius: 24px;
  padding: 16px;
}
.telegram-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  color: #526158;
  font-size: 12px;
  font-weight: 700;
}
.telegram-body {
  background: #fff;
  border-radius: 20px;
  padding: 16px;
  box-shadow: inset 0 0 0 1px rgba(24, 33, 28, 0.06);
  line-height: 1.55;
  font-size: 14px;
}
.telegram-body p {
  margin: 0 0 12px;
}
.telegram-body blockquote {
  margin: 0 0 12px;
  padding: 10px 12px;
  border-left: 3px solid rgba(31, 93, 74, 0.34);
  color: #4f5e55;
  background: rgba(31, 93, 74, 0.05);
  border-radius: 10px;
}
.release-workbench {
  display: grid;
  gap: 18px;
}
.release-intro h3 {
  margin: 0;
  font-size: 18px;
}
.release-stream {
  background: linear-gradient(180deg, #e9f2ea 0%, #dbe8dc 100%);
  border: 1px solid rgba(24, 33, 28, 0.08);
  border-radius: 24px;
  padding: 12px;
}
.release-stream-body {
  background: #fff;
  border-radius: 20px;
  padding: 16px;
  box-shadow: inset 0 0 0 1px rgba(24, 33, 28, 0.06);
  display: grid;
  gap: 16px;
}
.release-title-copy {
  font-size: 14px;
  line-height: 1.55;
  padding-bottom: 2px;
}
.release-title-copy b {
  display: block;
  margin-bottom: 4px;
}
.release-title-date {
  color: var(--muted);
  font-size: 13px;
}
.release-section {
  display: grid;
  gap: 10px;
}
.release-section-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: start;
  padding: 0;
  color: #7a5a11;
  font-size: 13px;
  font-weight: 700;
}
.release-row {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, .95fr);
  gap: 14px;
  align-items: start;
  min-width: 0;
}
.release-row.needs-attention .release-controls {
  border-color: rgba(156, 108, 31, 0.28);
  background: rgba(255, 247, 232, 0.82);
}
.release-preview {
  min-width: 0;
}
.release-preview-fragment {
  line-height: 1.55;
  font-size: 14px;
}
.release-preview-fragment p {
  margin: 0 0 12px;
}
.release-preview-fragment p:last-child,
.release-preview-fragment blockquote:last-child {
  margin-bottom: 0;
}
.release-preview-fragment blockquote {
  margin: 0 0 12px;
  padding: 10px 12px;
  border-left: 3px solid rgba(31, 93, 74, 0.34);
  color: #4f5e55;
  background: rgba(31, 93, 74, 0.05);
  border-radius: 10px;
}
.release-controls {
  display: grid;
  gap: 10px;
  padding: 10px 0 0 12px;
  border-radius: 0;
  border: none;
  background: transparent;
  min-width: 0;
}
.release-controls-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  min-width: 0;
}
.release-controls-grid select {
  width: 100%;
  min-width: 0;
  height: 40px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.92);
  padding: 0 10px;
  font-size: 12px;
}
.release-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
}
.release-note {
  font-size: 12px;
  color: var(--warn);
  font-weight: 700;
}
.related-editor-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}
.related-editor-item {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-right: 10px;
  margin-bottom: 8px;
  padding: 0;
  border-radius: 0;
  background: transparent;
}
.related-editor-item form {
  display: inline-flex;
  max-width: 100%;
}
.related-editor-prefix {
  font-size: 13px;
  color: #4f5e55;
  font-style: italic;
}
.related-editor-name {
  min-width: 0;
  font-size: 13px;
  color: #4f5e55;
}
.release-grouping-inline {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  min-width: 0;
}
.release-grouping-inline label {
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
}
.release-grouping-inline select {
  min-width: 0;
  max-width: 100%;
  flex: 1 1 240px;
  height: 36px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.92);
  padding: 0 10px;
  font-size: 12px;
}
.archive-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, .85fr);
  gap: 16px;
}
.archive-main,
.archive-rail {
  display: grid;
  gap: 16px;
}
.archive-block {
  background: var(--surface);
  backdrop-filter: blur(18px);
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 28px;
  padding: 18px;
  box-shadow: var(--shadow);
}
.archive-block h3 {
  margin: 0 0 10px;
  font-size: 18px;
}
.digest-strip {
  display: grid;
  gap: 10px;
}
.digest-card {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(24, 33, 28, 0.08);
  background: rgba(252, 250, 246, 0.92);
}
.digest-card.active {
  border-color: rgba(31, 93, 74, 0.24);
  background: rgba(232, 243, 238, 0.88);
}
.archive-review-stats {
  display: grid;
  gap: 10px;
}
.archive-stat {
  padding: 12px 14px;
  border-radius: 16px;
  background: rgba(252, 250, 246, 0.92);
  border: 1px solid rgba(24, 33, 28, 0.08);
}
.archive-stat strong {
  display: block;
  margin-bottom: 4px;
}
.rejected-backlog {
  display: grid;
  gap: 12px;
}
.rejected-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: start;
  padding: 14px;
  border-radius: 18px;
  background: rgba(252, 250, 246, 0.92);
  border: 1px solid rgba(24, 33, 28, 0.08);
}
.rejected-copy strong {
  display: block;
  margin-bottom: 6px;
  line-height: 1.35;
}
.rejected-copy .subline {
  margin-top: 0;
}
.rejected-copy .summary-box {
  margin-top: 10px;
}
.editor-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
}
.editor-item {
  padding: 14px;
  border-radius: 18px;
  background: rgba(252, 250, 246, 0.92);
  border: 1px solid rgba(24, 33, 28, 0.08);
}
.editor-item strong {
  display: block;
  margin-bottom: 8px;
  line-height: 1.35;
}
.editor-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 12px;
}
.editor-form {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr auto;
  gap: 8px;
}
.editor-form select {
  width: 100%;
  height: 40px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.92);
  padding: 0 10px;
  font-size: 12px;
}
.editor-link {
  color: var(--primary);
  text-decoration: none;
  font-size: 12px;
  font-weight: 700;
}
.editor-actions {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}
.tiny-actions.compact {
  gap: 6px;
}
.tiny-actions.compact .tiny-btn {
  min-height: 34px;
  padding: 0 10px;
  font-size: 11px;
}
.article {
  padding: 18px;
}
.article-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 390px;
  gap: 16px;
}
.article-main {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 14px;
  min-width: 0;
}
.select-col {
  padding-top: 3px;
}
.row-checkbox, #select-all {
  width: 18px;
  height: 18px;
  accent-color: var(--primary);
}
.article-top {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(24, 33, 28, 0.06);
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
}
.chip.keep-yes { background: rgba(31, 93, 74, 0.12); color: var(--primary); }
.chip.keep-no { background: rgba(160, 72, 54, 0.12); color: var(--danger); }
.chip.keep-null { background: rgba(24, 33, 28, 0.08); color: var(--muted); }
.chip.sent { background: rgba(217, 195, 122, 0.28); color: #7a5a11; }
.chip.failed { background: rgba(160, 72, 54, 0.12); color: var(--danger); }
.chip.built, .chip.empty { background: rgba(217, 195, 122, 0.28); color: #7a5a11; }
.chip.event { background: rgba(217, 195, 122, 0.2); color: #7a5a11; }
.article-title {
  display: inline-block;
  margin-bottom: 10px;
  font-size: 21px;
  font-weight: 700;
  line-height: 1.18;
  text-decoration: none;
}
.article-title:hover { text-decoration: underline; }
.article-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
  color: var(--muted);
  font-size: 13px;
}
.tag-stack {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.tag {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 11px;
  border-radius: 999px;
  background: rgba(31, 93, 74, 0.08);
  color: var(--primary-strong);
  font-size: 12px;
  font-weight: 700;
}
.summary-box {
  padding: 14px;
  border-radius: 18px;
  background: rgba(251, 249, 244, 0.96);
  border: 1px solid rgba(24, 33, 28, 0.08);
  color: #2b3a32;
  font-size: 14px;
  line-height: 1.55;
}
.summary-box.muted {
  color: var(--muted);
  font-style: italic;
}
.article-actions {
  display: grid;
  gap: 10px;
}
.action-card {
  padding: 14px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(24, 33, 28, 0.08);
}
.action-card h4 {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--muted);
}
.inline-form {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.inline-form select {
  width: 100%;
  height: 42px;
  border-radius: 13px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.92);
  padding: 0 10px;
  font-size: 12px;
}
.tiny-actions {
  display: flex;
  gap: 8px;
}
.tiny-btn {
  border: none;
  border-radius: 13px;
  min-height: 42px;
  padding: 0 12px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  cursor: pointer;
}
.save-btn { background: linear-gradient(135deg, var(--primary), var(--primary-strong)); }
.reprocess-btn { background: linear-gradient(135deg, #6c58bc, #503da3); }
.reset-btn { background: linear-gradient(135deg, #bf8124, #9d6417); }
.pagination {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.pagination a, .pagination span {
  min-width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  padding: 0 12px;
  font-size: 13px;
}
.pagination a {
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.84);
  color: var(--ink);
}
.pagination a.current {
  background: linear-gradient(135deg, var(--primary), var(--primary-strong));
  border-color: transparent;
  color: #fff;
}
.pagination a.disabled {
  opacity: .45;
  pointer-events: none;
}
.page-info {
  margin-left: auto;
  color: var(--muted);
  font-size: 13px;
}
@media (max-width: 1240px) {
  .workspace-grid, .workspace-grid.secondary, .article-layout, .archive-layout { grid-template-columns: 1fr; }
  .release-row { grid-template-columns: 1fr; }
  .rejected-card { grid-template-columns: 1fr; }
  .filters-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .filter-actions { grid-column: span 3; }
}
@media (max-width: 760px) {
  .page { padding: 16px 14px 28px; }
  .filters-shell, .workspace, .article, .digest-preview { border-radius: 22px; }
  .filters-grid, .inline-form, .release-controls-grid { grid-template-columns: 1fr; }
  .filter-actions { grid-column: auto; }
  .article-main { grid-template-columns: 1fr; }
  .select-col { order: -1; }
  .tiny-actions { flex-direction: column; }
  .page-info { margin-left: 0; width: 100%; }
  .release-controls { padding-left: 0; }
  .release-grouping-inline { flex-direction: column; align-items: stretch; }
  .release-grouping-inline select { width: 100%; flex-basis: auto; }
  .related-editor-item { display: flex; flex-direction: column; align-items: stretch; margin-right: 0; }
  .related-editor-item form,
  .related-editor-item .tiny-btn,
  .release-links form,
  .release-links .tiny-btn { width: 100%; }
}
</style>
</head>
<body>
<div class="page">
  <section class="topline">
    <h1>{{ panel_heading }}</h1>
    <p>{{ panel_intro }}</p>
  </section>

  <nav class="top-tabs">
    <a href="{{ panel_urls.release }}" class="pill {% if panel == 'release' %}active{% endif %}">Предстоящий дайджест</a>
    <a href="{{ panel_urls.delivery }}" class="pill {% if panel == 'delivery' %}active{% endif %}">Статус отправки</a>
    <a href="{{ panel_urls.archive }}" class="pill {% if panel == 'archive' %}active{% endif %}">Архив и исправления</a>
  </nav>

  <section class="workspace {% if panel == 'archive' %}archive-workspace{% endif %}">
    {% if panel == 'release' %}
    <div class="panel">
      <div class="release-workbench">
        <div class="release-intro">
          <h3>Предстоящий выпуск как сообщение в Telegram</h3>
        </div>
        {% if release_sections %}
        <div class="release-stream">
          <div class="release-stream-body">
            <div class="release-title-copy">
              <b>{{ digest_preview.digest_title if digest_preview else 'Юридический дайджест' }}</b>
              <div class="release-title-date">
                {% if digest_preview and digest_preview.digest_date_label %}
                за {{ digest_preview.digest_date_label }}
                {% endif %}
                {% if next_digest_total %}
                · {{ next_digest_total }} материалов
                {% endif %}
              </div>
            </div>
            {% for section in release_sections %}
            <section class="release-section">
              <div class="release-section-title">→ {{ section.title }}</div>
              {% for a in section.entries %}
              <div class="release-row {% if a.needs_attention %}needs-attention{% endif %}" id="preview-{{ a.id }}">
                <div class="release-preview">
                  <div class="release-preview-fragment">{{ a.preview_html|safe }}</div>
                  {% if a.related_items %}
                  <div class="related-editor-list">
                    <div class="related-editor-prefix">Другие публикации по теме:</div>
                    {% for related in a.related_items %}
                    <div class="related-editor-item">
                      <span class="related-editor-name">{{ related.title }}</span>
                      <form method="post" action="/article/{{ related.id }}/group">
                        <input type="hidden" name="next" value="{{ current_location }}">
                        <input type="hidden" name="group_parent" value="__self__">
                        <button type="submit" class="tiny-btn reset-btn">Вытащить из темы</button>
                      </form>
                    </div>
                    {% endfor %}
                  </div>
                  {% endif %}
                </div>
                <div class="release-controls">
                  {% if a.needs_attention %}
                  <div class="release-note">Эта новость требует внимания: проверь тип и тег перед отправкой.</div>
                  {% endif %}
                  <form method="post" action="/article/{{ a.id }}/update" class="release-controls-grid">
                    <input type="hidden" name="next" value="{{ current_location }}">
                    <select name="keep" onchange="this.form.requestSubmit()">
                      <option value="null" {% if a.keep is none %}selected{% endif %}>— Решение</option>
                      <option value="1" {% if a.keep is true %}selected{% endif %}>✓ В дайджест</option>
                      <option value="0" {% if a.keep is false %}selected{% endif %}>✗ Отклонить</option>
                    </select>
                    <select name="event_type" onchange="this.form.requestSubmit()">
                      <option value="">Тип</option>
                      {% for option in event_type_options %}
                      <option value="{{ option }}" {% if a.event_type == option %}selected{% endif %}>{{ option }}</option>
                      {% endfor %}
                    </select>
                    <select name="tag" onchange="this.form.requestSubmit()">
                      <option value="">Тег</option>
                      {% for option in tag_options %}
                      <option value="{{ option }}" {% if a.tag_value == option %}selected{% endif %}>{{ option }}</option>
                      {% endfor %}
                    </select>
                    <button type="submit" class="tiny-btn save-btn" style="display:none;">Сохранить</button>
                  </form>
                  <form method="post" action="/article/{{ a.id }}/group" class="release-grouping-inline">
                    <input type="hidden" name="next" value="{{ current_location }}">
                    <label for="group-parent-{{ a.id }}">Опустить внутрь темы</label>
                    <select id="group-parent-{{ a.id }}" name="group_parent" onchange="this.form.requestSubmit()">
                      <option value="auto">Не менять</option>
                      {% for option in release_group_options %}
                      {% if option.id != a.id %}
                      <option value="{{ option.id }}">{{ option.title }}</option>
                      {% endif %}
                      {% endfor %}
                    </select>
                  </form>
                  <div class="release-links">
                    <div class="tiny-actions compact">
                      <form method="post" action="/article/{{ a.id }}/reset">
                        <input type="hidden" name="next" value="{{ current_location }}">
                        <button type="submit" class="tiny-btn reset-btn">Сбросить</button>
                      </form>
                    </div>
                  </div>
                </div>
              </div>
              {% endfor %}
            </section>
            {% endfor %}
          </div>
        </div>
        {% else %}
        <div class="empty">Сейчас в выпуске нет новостей для ручной правки.</div>
        {% endif %}
        {% if rejected_release_candidates %}
        <section class="archive-block">
          <h3>Отложенные рядом с выпуском</h3>
          <div class="panel-meta">Это новости из того же окна, которые были отсеяны, но их можно вернуть в выпуск одним действием.</div>
          <div class="rejected-backlog">
            {% for a in rejected_release_candidates %}
            <div class="rejected-card">
              <div class="rejected-copy">
                <strong>{{ a.title }}</strong>
                <div class="subline">{{ a.pub_date }}</div>
                {% if a.reason %}
                <div class="summary-box muted">{{ a.reason }}</div>
                {% elif a.summary %}
                <div class="summary-box muted">{{ a.summary }}</div>
                {% endif %}
              </div>
              <form method="post" action="/article/{{ a.id }}/update">
                <input type="hidden" name="next" value="{{ current_location }}">
                <input type="hidden" name="keep" value="1">
                <input type="hidden" name="event_type" value="{{ a.event_type }}">
                <input type="hidden" name="tag" value="{{ a.tag_value }}">
                <select name="group_parent" style="display:none;">
                  <option value=""></option>
                </select>
                <button type="submit" class="tiny-btn save-btn">Закинуть в дайджест</button>
              </form>
              <form method="post" action="/article/{{ a.id }}/group">
                <input type="hidden" name="next" value="{{ current_location }}">
                <input type="hidden" name="promote_on_group" value="1">
                <input type="hidden" name="event_type" value="{{ a.event_type }}">
                <input type="hidden" name="tag" value="{{ a.tag_value }}">
                <select name="group_parent" onchange="this.form.requestSubmit()">
                  <option value="__self__">Добавить отдельной темой</option>
                  {% for option in release_group_options %}
                  <option value="{{ option.id }}">Добавить к теме: {{ option.title }}</option>
                  {% endfor %}
                </select>
              </form>
            </div>
            {% endfor %}
          </div>
        </section>
        {% endif %}
      </div>
    </div>
    {% elif panel == 'delivery' %}
    <div class="workspace-grid single">
      <div class="panel">
        <h3>Журнал отправки дайджестов</h3>
        <div class="panel-meta">Здесь хранится история всех попыток отправки. Если выпуск не ушел, рядом видно ошибку и можно сразу повторить отправку с сервера.</div>
        <div class="metric-row">
          <div class="metric">
            <div class="metric-label">Всего попыток</div>
            <div class="metric-value">{{ digest_runs|length }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Ошибок отправки</div>
            <div class="metric-value">{{ failed_runs_count }}</div>
          </div>
          <div class="metric">
            <div class="metric-label">Успешных отправок</div>
            <div class="metric-value">{{ sent_runs_count }}</div>
          </div>
        </div>
        {% if digest_runs %}
        <ul class="run-history">
          {% for item in digest_runs %}
          <li class="run-item {{ item.status_class }}">
            <div class="run-top">
              <strong>{{ item.digest_label }}</strong>
              <span class="chip {{ item.status_class }}">{{ item.status_label }}</span>
            </div>
            <div class="subline">{{ item.meta }}</div>
            {% if item.error_message %}
            <div class="run-error">{{ item.error_message }}</div>
            {% endif %}
            {% if item.can_retry %}
            <div class="run-actions">
              <form method="post" action="/delivery/{{ item.id }}/retry">
                <button type="submit" class="tiny-btn reprocess-btn">{{ item.retry_label }}</button>
              </form>
            </div>
            {% endif %}
          </li>
          {% endfor %}
        </ul>
        {% else %}
        <div class="empty">Пока нет истории сборок и отправок.</div>
        {% endif %}
      </div>
    </div>
    {% else %}
    <div class="archive-layout">
      <div class="archive-main">
        <section class="archive-block">
          <h3>Архив выпусков</h3>
          {% if sent_digest_groups %}
          <div class="digest-strip">
            {% for item in sent_digest_groups %}
            <a href="{{ item.url }}" class="digest-card {% if item.active %}active{% endif %}" style="text-decoration:none;">
              <div class="digest-main">
                <strong>{{ item.label }}</strong>
                <div class="subline">{{ item.subtitle }}</div>
              </div>
              <div class="digest-count">{{ item.count }}</div>
            </a>
            {% endfor %}
          </div>
          {% else %}
          <div class="empty">Пока нет ни одного отправленного выпуска.</div>
          {% endif %}
        </section>

        {% if digest_preview %}
        <section class="archive-block">
          <h3>{{ digest_preview.digest_title }}</h3>
          <div class="telegram-mock">
            <div class="telegram-body">{{ digest_preview.html|safe }}</div>
          </div>
        </section>
        {% endif %}
      </div>

      <aside class="archive-rail">
        <section class="archive-block">
          <h3>Исправления</h3>
          <div style="margin-bottom: 12px;">
            <a href="/archive/reviews" class="btn-ghost">Открыть весь журнал</a>
          </div>
          <div class="archive-review-stats">
            <div class="archive-stat">
              <strong>Всего</strong>
              <div class="subline">{{ review_stats.total }} записей</div>
            </div>
            <div class="archive-stat">
              <strong>По архиву</strong>
              <div class="subline">{{ review_stats.archive }} записей</div>
            </div>
            <div class="archive-stat">
              <strong>По будущим выпускам</strong>
              <div class="subline">{{ review_stats.future }} записей</div>
            </div>
          </div>
        </section>

      </aside>
    </div>
    {% endif %}
  </section>

  {% if panel == 'archive' %}
  <section class="filters-shell">
    <div class="section-head">
      <div>
        <h2>{{ feed_title }}</h2>
        <p>{{ feed_subtitle }}</p>
      </div>
    </div>

    <div class="filter-pills">
      <a href="{{ quick_urls.all }}" class="pill {% if quick_active == 'all' %}neutral-active{% endif %}">{{ all_pill_label }}</a>
      {% if panel == 'release' %}
      <a href="{{ quick_urls.keep_null }}" class="pill {% if quick_active == 'keep_null' %}active{% endif %}">Без решения</a>
      <a href="{{ quick_urls.keep_true }}" class="pill {% if quick_active == 'keep_true' %}active{% endif %}">Только ✓</a>
      {% else %}
      <a href="{{ quick_urls.sent }}" class="pill {% if quick_active == 'sent' %}active{% endif %}">Отправленные</a>
      <a href="{{ quick_urls.keep_false }}" class="pill {% if quick_active == 'keep_false' %}active{% endif %}">Только ✗</a>
      <a href="{{ quick_urls.keep_true }}" class="pill {% if quick_active == 'keep_true' %}active{% endif %}">Только ✓</a>
      {% endif %}
      <a href="{{ quick_urls.errors }}" class="pill {% if quick_active == 'errors' %}active{% endif %}">С ошибками</a>
    </div>

    <details>
      <summary>Дополнительные фильтры</summary>
      <form method="get" action="{{ current_path }}" style="margin-top: 14px;">
      {% if focus_filter %}
      <input type="hidden" name="focus" value="{{ focus_filter }}">
      {% endif %}
      {% if sent_digest_filter %}
      <input type="hidden" name="sent_digest" value="{{ sent_digest_filter }}">
      {% endif %}
      <div class="filters-grid">
        <div class="field">
          <label>Поиск по заголовку</label>
          <input type="text" name="q" value="{{ q }}" placeholder="Например: маркетплейс, ФАС, биометрия">
        </div>
        <div class="field">
          <label>Источник</label>
          <select name="source">
            <option value="">Все источники</option>
            {% for s in sources %}
            <option value="{{ s }}" {% if source_filter == s %}selected{% endif %}>{{ s }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="field">
          <label>Тип события</label>
          <select name="event_type">
            <option value="">Все типы</option>
            {% for et in event_types %}
            <option value="{{ et }}" {% if event_type_filter == et %}selected{% endif %}>{{ et }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="field">
          <label>Статус</label>
          <select name="status">
            <option value="">Все статусы</option>
            {% for status in statuses %}
            <option value="{{ status }}" {% if status_filter == status %}selected{% endif %}>{{ status }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="field">
          <label>Дата с</label>
          <input type="date" name="date_from" value="{{ date_from }}">
        </div>
        <div class="field">
          <label>Дата по</label>
          <input type="date" name="date_to" value="{{ date_to }}">
        </div>
        <div class="filter-actions">
          <button type="submit" class="btn">Применить</button>
          <a href="{{ reset_url }}" class="btn-soft">Сбросить</a>
        </div>
      </div>
      </form>
    </details>
  </section>

  <section class="feed">
    {% for a in articles %}
    <article class="article">
      <div class="article-layout">
        <div class="article-main">
          <div>
            <div class="article-top">
              {% if a.keep is none %}
                <span class="chip keep-null">Не решено</span>
              {% elif a.keep %}
                <span class="chip keep-yes">✓ В дайджест</span>
              {% else %}
                <span class="chip keep-no">✗ Отклонено</span>
              {% endif %}
              {% if a.event_type %}
                <span class="chip event">{{ a.event_type }}</span>
              {% endif %}
              <span class="chip">{{ a.processing_status or '—' }}</span>
              {% if a.sent_at %}
                <span class="chip sent">отправлено {{ a.sent_label }}</span>
              {% endif %}
            </div>

            <a class="article-title" href="{{ a.canonical_url }}" target="_blank">{{ a.title }}</a>

            <div class="article-meta">
              <span>{{ a.source_name }}</span>
              <span>{{ a.pub_date }}</span>
              {% if a.decision_source %}
              <span>решение: {{ a.decision_source }}</span>
              {% endif %}
            </div>

            <div class="tag-stack">
              {% for tag in (a.tags or []) %}
              <span class="tag">{{ tag }}</span>
              {% endfor %}
              {% if not a.tags %}
              <span class="tag">без тега</span>
              {% endif %}
            </div>

            {% if a.keep and a.llm_summary %}
            <div class="summary-box">{{ a.llm_summary }}</div>
            {% elif not a.keep and a.reason %}
            <div class="summary-box muted">{{ a.reason }}</div>
            {% elif a.fetch_error or a.classify_error %}
            <div class="summary-box muted">{{ a.fetch_error or a.classify_error }}</div>
            {% else %}
            <div class="summary-box muted">По этой статье пока нет редакторского комментария или резюме.</div>
            {% endif %}
          </div>
        </div>

        <aside class="article-actions">
          <form method="post" action="/article/{{ a.id }}/update" class="action-card">
            <input type="hidden" name="next" value="{{ current_location }}">
            <h4>Редактирование статьи</h4>
            <div class="inline-form">
              <select name="keep">
                <option value="null" {% if a.keep is none %}selected{% endif %}>— Решение</option>
                <option value="1" {% if a.keep is true %}selected{% endif %}>✓ В дайджест</option>
                <option value="0" {% if a.keep is false %}selected{% endif %}>✗ Отклонить</option>
              </select>
              <select name="event_type">
                <option value="">Тип</option>
                {% for option in event_type_options %}
                <option value="{{ option }}" {% if a.event_type == option %}selected{% endif %}>{{ option }}</option>
                {% endfor %}
              </select>
              <select name="tag">
                <option value="">Тег</option>
                {% for option in tag_options %}
                <option value="{{ option }}" {% if a.tag_value == option %}selected{% endif %}>{{ option }}</option>
                {% endfor %}
              </select>
              <button type="submit" class="tiny-btn save-btn">Сохранить</button>
            </div>
          </form>

          <div class="action-card">
            <h4>Быстрые действия</h4>
            <div class="tiny-actions">
              <form method="post" action="/article/{{ a.id }}/reprocess">
                <input type="hidden" name="next" value="{{ current_location }}">
                <button type="submit" class="tiny-btn reprocess-btn">Переобработать</button>
              </form>
              <form method="post" action="/article/{{ a.id }}/reset">
                <input type="hidden" name="next" value="{{ current_location }}">
                <button type="submit" class="tiny-btn reset-btn">Сбросить</button>
              </form>
            </div>
          </div>
        </aside>
      </div>
    </article>
    {% else %}
    <div class="article empty">Статей не найдено. Попробуй ослабить фильтры или открыть другой отправленный выпуск.</div>
    {% endfor %}
  </section>

  <nav class="pagination">
    {% if page > 1 %}
      <a href="{{ page_url(page-1) }}">←</a>
    {% else %}
      <a class="disabled">←</a>
    {% endif %}

    {% for p in page_range %}
      {% if p == page %}
        <a class="current">{{ p }}</a>
      {% elif p == '...' %}
        <span>…</span>
      {% else %}
        <a href="{{ page_url(p) }}">{{ p }}</a>
      {% endif %}
    {% endfor %}

    {% if page < total_pages %}
      <a href="{{ page_url(page+1) }}">→</a>
    {% else %}
      <a class="disabled">→</a>
    {% endif %}

    <div class="page-info">Страница {{ page }} из {{ total_pages }}</div>
  </nav>
  {% endif %}
</div>
</body>
</html>
"""

REVIEWS_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Архив исправлений — Legal Digest</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {
  margin: 0;
  font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
  background: linear-gradient(180deg, #faf7f1 0%, #f4f1ea 100%);
  color: #18211c;
}
.page {
  max-width: 980px;
  margin: 0 auto;
  padding: 22px 16px 36px;
}
.back {
  display: inline-flex;
  margin-bottom: 14px;
  color: #1f5d4a;
  text-decoration: none;
  font-weight: 700;
}
.card {
  background: rgba(255, 252, 246, 0.9);
  border: 1px solid rgba(24, 33, 28, 0.08);
  border-radius: 24px;
  box-shadow: 0 22px 52px rgba(42, 44, 31, 0.12);
  padding: 20px;
}
.card h1 {
  margin: 0 0 8px;
  font-size: 24px;
}
.sub {
  color: #647066;
  line-height: 1.5;
  margin-bottom: 18px;
}
.review-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
}
.review-item {
  border: 1px solid rgba(24, 33, 28, 0.08);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
  padding: 14px;
}
.review-item strong {
  display: block;
  margin-bottom: 6px;
}
.meta {
  color: #647066;
  font-size: 13px;
  margin-bottom: 6px;
}
.empty {
  color: #647066;
}
</style>
</head>
<body>
<div class="page">
  <a class="back" href="/archive">← Назад в архив</a>
  <section class="card">
    <h1>Архив исправлений</h1>
    <div class="sub">Здесь хранится история ручных исправлений по статьям. Это отдельный журнал для разбора прошлых решений и будущего обучения модели.</div>
    {% if recent_reviews %}
    <ul class="review-list">
      {% for item in recent_reviews %}
      <li class="review-item">
        <strong>{{ item.title }}</strong>
        <div class="meta">{{ item.created_at }} · {{ item.action_label }} · {{ item.review_scope_label }}</div>
        <div>{{ item.diff }}</div>
      </li>
      {% endfor %}
    </ul>
    {% else %}
    <div class="empty">Пока ручных исправлений нет.</div>
    {% endif %}
  </section>
</div>
</body>
</html>
"""


def _page_url(base_args: dict, p: int) -> str:
    path = base_args.get("_path", "/")
    args = {k: v for k, v in {**base_args, "page": p}.items() if k != "_path"}
    query = urlencode({k: v for k, v in args.items() if v not in (None, "", False)})
    return path if not query else f"{path}?{query}"


def _query_url(base_args: dict, **updates: str) -> str:
    path = base_args.get("_path", "/")
    args = {k: v for k, v in base_args.items() if k != "_path"}
    for key, value in updates.items():
        if value in (None, ""):
            args.pop(key, None)
        else:
            args[key] = value
    args.pop("page", None)
    query = urlencode({k: v for k, v in args.items() if v not in (None, "", False)})
    return path if not query else f"{path}?{query}"


def _page_range(page: int, total_pages: int) -> list:
    if total_pages <= 9:
        return list(range(1, total_pages + 1))
    pages: list = []
    for p in range(1, total_pages + 1):
        if p == 1 or p == total_pages or abs(p - page) <= 2:
            pages.append(p)
        elif pages and pages[-1] != "...":
            pages.append("...")
    return pages


def _redirect_back(next_value: str | None) -> str:
    next_value = (next_value or "").strip()
    if not next_value:
        return "/"
    if next_value.startswith("/"):
        return next_value
    return f"/?{next_value}"


def _parse_keep(value: str) -> bool | None:
    value = (value or "").strip().lower()
    if value == "1":
        return True
    if value == "0":
        return False
    return None


def _normalize_article_tags(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        for tag in raw:
            if isinstance(tag, str) and tag in TAG_OPTIONS:
                return [tag]
        return []
    if isinstance(raw, str) and raw in TAG_OPTIONS:
        return [raw]
    return []


def _parse_tag(value: str) -> list[str]:
    value = (value or "").strip()
    if value in TAG_OPTIONS:
        return [value]
    return []


def _primary_tag(raw: object) -> str | None:
    tags = _normalize_article_tags(raw)
    return tags[0] if tags else None


def _review_scope(article: Article) -> str:
    return "archive" if article.sent_at is not None else "future"


def _record_review(
    db,
    *,
    article: Article,
    action: str,
    previous_keep: bool | None,
    previous_event_type: str | None,
    previous_tag: str | None,
) -> None:
    db.add(
        ArticleReview(
            article_id=article.id,
            action=action,
            review_scope=_review_scope(article),
            previous_keep=previous_keep,
            new_keep=article.keep,
            previous_event_type=previous_event_type,
            new_event_type=article.event_type,
            previous_tag=previous_tag,
            new_tag=_primary_tag(article.tags),
        )
    )


def _preview_items(rows: list[Article]) -> list[dict]:
    preview = []
    for article in rows[:7]:
        preview.append(
            {
                "title": article.title,
                "url": article.canonical_url,
                "source": article.source_name,
                "event_type": article.event_type,
            }
        )
    return preview


def _sent_digest_bounds(iso_day: str) -> tuple[datetime, datetime, str] | None:
    try:
        day = date.fromisoformat(iso_day)
    except ValueError:
        return None
    start_local = datetime.combine(day, time.min, tzinfo=LOCAL_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc), start_local.strftime("%d.%m.%Y")


def _sent_digest_groups(rows: list[datetime], active_iso_day: str, base_args: dict) -> list[dict]:
    grouped: dict[str, dict] = {}
    for sent_at in rows:
        local_day = sent_at.astimezone(LOCAL_TZ).date()
        iso_day = local_day.isoformat()
        item = grouped.setdefault(
            iso_day,
            {
                "iso_day": iso_day,
                "label": local_day.strftime("%d.%m.%Y"),
                "count": 0,
                "latest": sent_at,
            },
        )
        item["count"] += 1
        if sent_at > item["latest"]:
            item["latest"] = sent_at

    result = []
    for iso_day, item in sorted(grouped.items(), key=lambda pair: pair[1]["latest"], reverse=True)[:10]:
        result.append(
            {
                "label": item["label"],
                "subtitle": "открыть статьи из этого выпуска",
                "count": item["count"],
                "active": iso_day == active_iso_day,
                "url": _query_url({**base_args, "_path": _panel_base_path("archive")}, focus="", sent_digest=iso_day, sent="1"),
            }
        )
    return result


def _resolve_quick_active(
    keep_filter: str,
    sent_filter: str,
    errors_only: bool,
    source_filter: str,
    event_type_filter: str,
    status_filter: str,
    date_from: str,
    date_to: str,
    q: str,
) -> str:
    if source_filter or event_type_filter or status_filter or date_from or date_to or q:
        return ""
    if errors_only:
        return "errors"
    if keep_filter == "1" and not sent_filter:
        return "keep_true"
    if keep_filter == "0" and not sent_filter:
        return "keep_false"
    if keep_filter == "null" and not sent_filter:
        return "keep_null"
    if sent_filter == "0" and not keep_filter:
        return "unsent"
    if sent_filter == "1" and not keep_filter:
        return "sent"
    if not keep_filter and not sent_filter and not errors_only:
        return "all"
    return ""


def _review_action_label(action: str) -> str:
    labels = {
        "update": "ручная правка",
        "reprocess": "переобработка",
        "reset": "сброс",
        "bulk_keep_true": "массово: взять",
        "bulk_keep_false": "массово: отклонить",
        "bulk_manual_review": "массово: ручной разбор",
        "bulk_reprocess": "массово: переобработать",
        "bulk_reset": "массово: сбросить",
    }
    return labels.get(action, action)


def _review_scope_label(scope: str) -> str:
    return "архив" if scope == "archive" else "будущий выпуск"


def _review_diff(item: ArticleReview) -> str:
    before = [item.previous_keep, item.previous_event_type, item.previous_tag]
    after = [item.new_keep, item.new_event_type, item.new_tag]
    if before == after:
        return "значения не менялись, но действие зафиксировано"
    return (
        f"решение: {item.previous_keep!s} -> {item.new_keep!s} · "
        f"тип: {item.previous_event_type or '—'} -> {item.new_event_type or '—'} · "
        f"тег: {item.previous_tag or '—'} -> {item.new_tag or '—'}"
    )


def _digest_status_label(status: str) -> str:
    labels = {
        "sent": "Успешно отправлен",
        "failed": "Ошибка отправки",
        "built": "Собран и ждет отправки",
        "empty": "Нечего отправлять",
    }
    return labels.get(status, status or "—")


def _digest_status_class(status: str) -> str:
    if status in {"sent", "failed", "built", "empty"}:
        return status
    return "empty"


def _digest_run_view(run: DigestRun) -> dict:
    started_local = run.started_at.astimezone(LOCAL_TZ) if run.started_at and run.started_at.tzinfo else run.started_at
    finished_local = run.finished_at.astimezone(LOCAL_TZ) if run.finished_at and run.finished_at.tzinfo else run.finished_at
    meta_parts = [
        f"окно {run.window_start.astimezone(LOCAL_TZ).strftime('%d.%m %H:%M')} - {run.window_end.astimezone(LOCAL_TZ).strftime('%d.%m %H:%M')}"
    ]
    if started_local:
        meta_parts.append(f"старт {started_local.strftime('%d.%m %H:%M')}")
    if finished_local:
        meta_parts.append(f"финиш {finished_local.strftime('%d.%m %H:%M')}")
    meta_parts.append(f"статей {run.article_count}")
    if run.sent_count:
        meta_parts.append(f"отправлено {run.sent_count}")
    return {
        "id": run.id,
        "digest_label": run.digest_date.strftime("%d.%m.%Y"),
        "status_label": _digest_status_label(run.status),
        "status_class": _digest_status_class(run.status),
        "meta": " · ".join(meta_parts),
        "error_message": run.error_message,
        "can_retry": run.status in {"failed", "built"},
        "retry_label": "Повторить отправку" if run.status == "failed" else "Отправить сейчас",
    }


def _format_digest_preview(rows: list[Article], title: str) -> str:
    if not rows:
        return "Новых материалов нет."

    lines: list[str] = [title]
    lines[0] = f"{title} из {len(rows)} материалов"

    grouped: dict[str, list[Article]] = {tag: [] for tag in TAG_ORDER}
    grouped["_other"] = []
    for article in rows:
        placed = False
        for tag in TAG_ORDER:
            if tag in _article_tags(article):
                grouped[tag].append(article)
                placed = True
                break
        if not placed:
            grouped["_other"].append(article)

    for tag in TAG_ORDER:
        items = grouped.get(tag, [])
        if not items:
            continue
        items_sorted = sorted(
            items,
            key=lambda article: (
                getattr(article, "published_at", None) is not None,
                getattr(article, "published_at", None) or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )[:15]
        lines.append("")
        lines.append(f"-> {TAG_TITLES[tag]}")
        for article in items_sorted:
            badge = EVENT_BADGE.get(article.event_type or "", "")
            title_part = re.sub(r"<[^>]+>", "", _render_title(article))
            lines.append("")
            lines.append(f"{badge} {title_part}" if badge else title_part)

            summary_text = _best_summary(article, 300)
            if summary_text:
                lines.append(summary_text)

    return html.unescape("\n".join(lines))


def _format_digest_preview_html(rows: list[Article], title: str) -> str:
    if not rows:
        return "<p><i>Новых материалов нет.</i></p>"

    parts: list[str] = [f"<p><b>{html.escape(title)} из {len(rows)} материалов</b></p>"]
    grouped: dict[str, list[Article]] = {tag: [] for tag in TAG_ORDER}
    grouped["_other"] = []

    for article in rows:
        placed = False
        for tag in TAG_ORDER:
            if tag in _article_tags(article):
                grouped[tag].append(article)
                placed = True
                break
        if not placed:
            grouped["_other"].append(article)

    for tag in TAG_ORDER:
        items = grouped.get(tag, [])
        if not items:
            continue
        items_sorted = sorted(
            items,
            key=lambda article: (
                getattr(article, "published_at", None) is not None,
                getattr(article, "published_at", None) or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )[:15]
        parts.append(f"<p><b>→ {html.escape(TAG_TITLES[tag])}</b></p>")
        for article in items_sorted:
            badge = EVENT_BADGE.get(article.event_type or "", "")
            title_part = _render_title(article)
            preview_id = f"preview-{article.id}" if getattr(article, "id", None) is not None else ""
            attr = f' id="{preview_id}"' if preview_id else ""
            parts.append(f"<p{attr}>{badge + ' ' if badge else ''}{title_part}</p>")
            summary_text = _best_summary(article, 300)
            if summary_text:
                parts.append(f"<blockquote>{html.escape(summary_text)}</blockquote>")

    return "\n".join(parts)


def _release_item_preview_html(article: Article) -> str:
    badge = EVENT_BADGE.get(article.event_type or "", "")
    title_part = _render_title(article)
    parts = [f"<p>{badge + ' ' if badge else ''}{title_part}</p>"]
    summary_text = _best_summary(article, 300)
    if summary_text:
        parts.append(f"<blockquote>{html.escape(summary_text)}</blockquote>")
    return "\n".join(parts)


def _build_release_sections(rows: list[Article]) -> list[dict]:
    grouped: dict[str, list[Article]] = {tag: [] for tag in TAG_ORDER}
    grouped["_other"] = []

    for article in rows:
        placed = False
        for tag in TAG_ORDER:
            if tag in _article_tags(article):
                grouped[tag].append(article)
                placed = True
                break
        if not placed:
            grouped["_other"].append(article)

    sections: list[dict] = []
    for tag in TAG_ORDER:
        items = grouped.get(tag, [])
        if not items:
            continue
        section_items = []
        for topic in _build_digest_topics(items)[:15]:
            article = topic["primary"]
            related = topic["related"]
            pub = getattr(article, "published_at", None) or getattr(article, "created_at", None)
            if pub and pub.tzinfo:
                pub = pub.astimezone(LOCAL_TZ)
            tag_value = _primary_tag(getattr(article, "tags", None))
            section_items.append(
                {
                    "id": getattr(article, "id", None),
                    "title": getattr(article, "title", ""),
                    "canonical_url": getattr(article, "canonical_url", ""),
                    "source_name": getattr(article, "source_name", ""),
                    "pub_date": pub.strftime("%d.%m.%Y") if pub else "—",
                    "event_type": getattr(article, "event_type", None),
                    "tag_value": tag_value or "",
                    "keep": getattr(article, "keep", None),
                    "processing_status": getattr(article, "processing_status", None),
                    "decision_source": getattr(article, "decision_source", None),
                    "preview_html": _release_item_preview_html(article),
                    "manual_group_parent_id": getattr(article, "manual_digest_parent_id", None),
                    "digest_force_standalone": bool(getattr(article, "digest_force_standalone", False)),
                    "needs_attention": not getattr(article, "event_type", None) or not tag_value,
                    "related_items": [
                        {
                            "id": related_article.id,
                            "title": related_article.title,
                            "source_name": related_article.source_name,
                            "manual_digest_parent_id": getattr(related_article, "manual_digest_parent_id", None),
                        }
                        for related_article in related
                    ],
                }
            )

        sections.append({"title": TAG_TITLES[tag], "entries": section_items})

    return sections


def _selected_archive_articles(rows: list[dict]) -> list[Article]:
    selected: list[Article] = []
    for item in rows:
        article = Article(
            id=item["id"],
            source_id="",
            source_name=item["source_name"],
            title=item["title"],
            url=item["canonical_url"],
            canonical_url=item["canonical_url"],
            content_hash=f"preview-{item['id']}",
            keep=item["keep"],
            event_type=item["event_type"],
            tags=item["tags"],
            published_at=None,
            llm_summary=item["llm_summary"] or None,
            llm_reason=item["reason"] or None,
        )
        selected.append(article)
    return selected


def _apply_bulk_action(article: Article, action: str, event_type: str, tags: list[str]) -> None:
    if action == "keep_true":
        article.keep = True
        article.processing_status = "manual_review"
        article.decision_source = "manual"
    elif action == "keep_false":
        article.keep = False
        article.processing_status = "manual_review"
        article.decision_source = "manual"
    elif action == "manual_review":
        article.processing_status = "manual_review"
        article.decision_source = "manual"
    elif action == "reprocess":
        article.keep = None
        article.event_type = None
        article.tags = None
        article.score = None
        article.topic = None
        article.llm_summary = None
        article.llm_reason = None
        article.decision_source = None
        article.classify_error = None
        article.fetch_error = None
        article.processing_status = "new"
        article.fetched_at = None
        article.last_processed_at = datetime.now(timezone.utc)
        return
    elif action == "reset":
        article.keep = None
        article.event_type = None
        article.tags = None
        article.score = None
        article.topic = None
        article.llm_summary = None
        article.llm_reason = None
        article.decision_source = None
        article.classify_error = None
        article.processing_status = "reset"
        article.last_processed_at = datetime.now(timezone.utc)
        return

    if event_type:
        article.event_type = event_type
        article.topic = event_type
    if tags:
        article.tags = tags
    article.classify_error = None
    article.last_processed_at = datetime.now(timezone.utc)


@app.post("/article/<int:article_id>/update")
def update_article(article_id: int):
    next_value = request.form.get("next", "")
    with SessionLocal() as db:
        article = db.get(Article, article_id)
        if article is None:
            return redirect(_redirect_back(next_value))

        previous_keep = article.keep
        previous_event_type = article.event_type
        previous_tag = _primary_tag(article.tags)
        article.keep = _parse_keep(request.form.get("keep", "null"))
        article.event_type = (request.form.get("event_type", "") or "").strip() or None
        article.tags = _parse_tag(request.form.get("tag", ""))
        article.topic = article.event_type
        article.decision_source = "manual"
        article.processing_status = "manual_review"
        article.classify_error = None
        article.last_processed_at = datetime.now(timezone.utc)
        _record_review(
            db,
            article=article,
            action="update",
            previous_keep=previous_keep,
            previous_event_type=previous_event_type,
            previous_tag=previous_tag,
        )
        db.commit()

    return redirect(_redirect_back(next_value))


def _apply_group_override(db, article: Article, raw_parent: str) -> None:
    raw_parent = (raw_parent or "").strip()
    article_id = getattr(article, "id", None)
    if article_id is None:
        return

    if raw_parent in {"", "auto"}:
        article.manual_digest_parent_id = None
        article.digest_force_standalone = False
        return

    if raw_parent == "__self__":
        article.manual_digest_parent_id = None
        article.digest_force_standalone = True
        return

    if not raw_parent.isdigit():
        return

    parent_id = int(raw_parent)
    if parent_id == article_id:
        article.manual_digest_parent_id = None
        article.digest_force_standalone = True
        return

    parent = db.get(Article, parent_id)
    if parent is None:
        return

    resolved_parent_id = getattr(parent, "manual_digest_parent_id", None) or parent.id
    if resolved_parent_id == article_id:
        article.manual_digest_parent_id = None
        article.digest_force_standalone = True
        return

    article.manual_digest_parent_id = resolved_parent_id
    article.digest_force_standalone = False


@app.post("/article/<int:article_id>/group")
def update_article_group(article_id: int):
    next_value = request.form.get("next", "")
    with SessionLocal() as db:
        article = db.get(Article, article_id)
        if article is None:
            return redirect(_redirect_back(next_value))

        previous_keep = article.keep
        previous_event_type = article.event_type
        previous_tag = _primary_tag(article.tags)
        if request.form.get("promote_on_group", "") == "1":
            article.keep = True
            event_type = (request.form.get("event_type", "") or "").strip()
            tag = (request.form.get("tag", "") or "").strip()
            article.event_type = event_type or article.event_type
            if tag:
                article.tags = _parse_tag(tag)
        _apply_group_override(db, article, request.form.get("group_parent", ""))
        article.decision_source = "manual"
        article.processing_status = "manual_review"
        article.last_processed_at = datetime.now(timezone.utc)
        _record_review(
            db,
            article=article,
            action="group_update",
            previous_keep=previous_keep,
            previous_event_type=previous_event_type,
            previous_tag=previous_tag,
        )
        db.commit()

    return redirect(_redirect_back(next_value))


@app.post("/article/<int:article_id>/reprocess")
def reprocess_article(article_id: int):
    next_value = request.form.get("next", "")
    with SessionLocal() as db:
        article = db.get(Article, article_id)
        if article is None:
            return redirect(_redirect_back(next_value))

        previous_keep = article.keep
        previous_event_type = article.event_type
        previous_tag = _primary_tag(article.tags)
        article.keep = None
        article.event_type = None
        article.tags = None
        article.score = None
        article.topic = None
        article.llm_summary = None
        article.llm_reason = None
        article.decision_source = None
        article.classify_error = None
        article.fetch_error = None
        article.processing_status = "new"
        article.fetched_at = None
        article.last_processed_at = datetime.now(timezone.utc)
        _record_review(
            db,
            article=article,
            action="reprocess",
            previous_keep=previous_keep,
            previous_event_type=previous_event_type,
            previous_tag=previous_tag,
        )
        db.commit()

    return redirect(_redirect_back(next_value))


@app.post("/article/<int:article_id>/reset")
def reset_article(article_id: int):
    next_value = request.form.get("next", "")
    with SessionLocal() as db:
        article = db.get(Article, article_id)
        if article is None:
            return redirect(_redirect_back(next_value))

        previous_keep = article.keep
        previous_event_type = article.event_type
        previous_tag = _primary_tag(article.tags)
        article.keep = None
        article.event_type = None
        article.tags = None
        article.score = None
        article.topic = None
        article.llm_summary = None
        article.llm_reason = None
        article.decision_source = None
        article.classify_error = None
        article.processing_status = "reset"
        article.last_processed_at = datetime.now(timezone.utc)
        _record_review(
            db,
            article=article,
            action="reset",
            previous_keep=previous_keep,
            previous_event_type=previous_event_type,
            previous_tag=previous_tag,
        )
        db.commit()

    return redirect(_redirect_back(next_value))


@app.post("/articles/bulk-update")
def bulk_update_articles():
    next_value = request.form.get("next", "")
    article_ids = [value for value in request.form.getlist("article_ids") if value.isdigit()]
    bulk_action = (request.form.get("bulk_action", "") or "").strip()
    bulk_event_type = (request.form.get("bulk_event_type", "") or "").strip()
    bulk_tags = _parse_tag(request.form.get("bulk_tag", ""))

    if not article_ids or not bulk_action:
        return redirect(_redirect_back(next_value))

    with SessionLocal() as db:
        rows = db.execute(select(Article).where(Article.id.in_([int(value) for value in article_ids]))).scalars().all()
        for article in rows:
            previous_keep = article.keep
            previous_event_type = article.event_type
            previous_tag = _primary_tag(article.tags)
            _apply_bulk_action(article, bulk_action, bulk_event_type, bulk_tags)
            _record_review(
                db,
                article=article,
                action=f"bulk_{bulk_action}",
                previous_keep=previous_keep,
                previous_event_type=previous_event_type,
                previous_tag=previous_tag,
            )
        db.commit()

    return redirect(_redirect_back(next_value))


@app.post("/delivery/<int:run_id>/retry")
def retry_delivery_run(run_id: int):
    with SessionLocal() as db:
        try:
            retry_digest_run(db, run_id)
        except ValueError:
            return redirect("/delivery")
        except Exception:
            return redirect("/delivery")
    return redirect("/delivery")


def _panel_base_path(panel: str) -> str:
    if panel == "delivery":
        return "/delivery"
    if panel == "archive":
        return "/archive"
    return "/"


def _render_panel(panel: str):
    focus_filter = request.args.get("focus", "").strip()
    keep_filter = request.args.get("keep", "")
    source_filter = request.args.get("source", "")
    event_type_filter = request.args.get("event_type", "")
    status_filter = request.args.get("status", "")
    sent_filter = request.args.get("sent", "")
    sent_digest_filter = request.args.get("sent_digest", "").strip()
    if sent_digest_filter:
        panel = "archive"
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    q = request.args.get("q", "").strip()
    errors_only = request.args.get("errors_only", "") == "1"
    page = max(1, int(request.args.get("page", 1) or 1))
    workspace = "archive" if panel == "archive" else "future"
    if panel == "release" and not focus_filter:
        focus_filter = "next_digest"

    base_args = {
        "_path": _panel_base_path(panel),
        "focus": focus_filter,
        "keep": keep_filter,
        "source": source_filter,
        "event_type": event_type_filter,
        "status": status_filter,
        "sent": sent_filter,
        "sent_digest": sent_digest_filter,
        "date_from": date_from,
        "date_to": date_to,
        "q": q,
        "errors_only": "1" if errors_only else "",
    }

    with SessionLocal() as db:
        digest_window = _resolve_digest_window()
        next_digest_rows = get_articles_for_digest(db, limit=200, window=digest_window)
        next_digest_attention_count = sum(
            1
            for article in next_digest_rows
            if not getattr(article, "event_type", None) or not _primary_tag(getattr(article, "tags", None))
        )
        next_digest_manual_count = sum(
            1 for article in next_digest_rows if getattr(article, "decision_source", "") == "manual"
        )

        sources = [r[0] for r in db.execute(select(Article.source_id).distinct().order_by(Article.source_id)).all()]
        event_types = [r[0] for r in db.execute(select(Article.event_type).where(Article.event_type.isnot(None)).distinct()).all()]
        statuses = [r[0] for r in db.execute(select(Article.processing_status).where(Article.processing_status.isnot(None)).distinct()).all()]
        total_all = db.scalar(select(func.count()).select_from(Article))

        stmt = select(Article).order_by(Article.created_at.desc())
        next_digest_ids = [article_id for article in next_digest_rows if (article_id := getattr(article, "id", None)) is not None]

        if panel == "release":
            stmt = stmt.where(Article.sent_at.is_(None))
        elif panel == "archive":
            archive_cutoff = digest_window[1]
            stmt = stmt.where(
                (Article.sent_at.isnot(None))
                | (
                    Article.keep.isnot(None)
                    & Article.published_at.isnot(None)
                    & (Article.published_at < archive_cutoff)
                )
            )

        if focus_filter == "next_digest":
            if next_digest_ids:
                stmt = stmt.where(Article.id.in_(next_digest_ids))
            else:
                stmt = stmt.where(Article.id == -1)

        if keep_filter == "1":
            stmt = stmt.where(Article.keep.is_(True))
        elif keep_filter == "0":
            stmt = stmt.where(Article.keep.is_(False))
        elif keep_filter == "null":
            stmt = stmt.where(Article.keep.is_(None))

        if source_filter:
            stmt = stmt.where(Article.source_id == source_filter)

        if event_type_filter:
            stmt = stmt.where(Article.event_type == event_type_filter)

        if status_filter:
            stmt = stmt.where(Article.processing_status == status_filter)

        if sent_filter == "1":
            stmt = stmt.where(Article.sent_at.isnot(None))
        elif sent_filter == "0":
            stmt = stmt.where(Article.sent_at.is_(None))

        sent_digest_filter_label = ""
        if sent_digest_filter:
            bounds = _sent_digest_bounds(sent_digest_filter)
            if bounds:
                start_utc, end_utc, sent_digest_filter_label = bounds
                stmt = stmt.where(Article.sent_at >= start_utc, Article.sent_at < end_utc)

        if date_from:
            dt = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            stmt = stmt.where(Article.created_at >= dt)
        if date_to:
            dt = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)
            stmt = stmt.where(Article.created_at < dt)

        if q:
            stmt = stmt.where(Article.title.ilike(f"%{q}%"))

        if errors_only:
            stmt = stmt.where((Article.fetch_error.isnot(None)) | (Article.classify_error.isnot(None)))

        sub = stmt.order_by(None).subquery()
        count_stmt = select(func.count(), sub.c.keep).group_by(sub.c.keep)
        count_keep = count_reject = count_null = 0
        for cnt, kp in db.execute(count_stmt).all():
            if kp is True:
                count_keep = cnt
            elif kp is False:
                count_reject = cnt
            else:
                count_null = cnt
        total = count_keep + count_reject + count_null

        digest_window_label = (
            f"{digest_window[0].astimezone(LOCAL_TZ).strftime('%d.%m %H:%M')} - "
            f"{digest_window[1].astimezone(LOCAL_TZ).strftime('%d.%m %H:%M')}"
        )

        sent_at_rows = [r[0] for r in db.execute(select(Article.sent_at).where(Article.sent_at.isnot(None)).order_by(Article.sent_at.desc())).all()]
        sent_digest_groups = _sent_digest_groups(sent_at_rows, sent_digest_filter, base_args)
        sent_digest_total = len(sent_digest_groups)
        digest_preview = None
        release_sections = []
        release_group_options = []
        rejected_release_candidates = []

        digest_runs = []
        latest_run = None
        failed_runs_count = 0
        sent_runs_count = 0
        if inspect(db.bind).has_table("digest_runs"):
            run_rows = db.execute(select(DigestRun).order_by(DigestRun.started_at.desc()).limit(8)).scalars().all()
            digest_runs = [_digest_run_view(run) for run in run_rows]
            latest_run = digest_runs[0] if digest_runs else None
            failed_runs_count = sum(1 for item in digest_runs if item["status_class"] == "failed")
            sent_runs_count = sum(1 for item in digest_runs if item["status_class"] == "sent")

        review_total = review_future = review_archive = 0
        if inspect(db.bind).has_table("article_reviews"):
            review_total = db.scalar(select(func.count()).select_from(ArticleReview)) or 0
            review_future = db.scalar(select(func.count()).select_from(ArticleReview).where(ArticleReview.review_scope == "future")) or 0
            review_archive = db.scalar(select(func.count()).select_from(ArticleReview).where(ArticleReview.review_scope == "archive")) or 0

        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, total_pages)

        rows = db.execute(stmt.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).scalars().all()
        archive_digest_rows: list[Article] = []
        if panel == "archive" and sent_digest_filter:
            bounds = _sent_digest_bounds(sent_digest_filter)
            if bounds:
                start_utc, end_utc, sent_digest_filter_label = bounds
                archive_digest_rows = db.execute(
                    select(Article)
                    .where(Article.sent_at >= start_utc, Article.sent_at < end_utc)
                    .where(Article.keep.is_(True))
                    .order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
                ).scalars().all()

        articles = []
        for a in rows:
            pub = a.published_at or a.created_at
            if pub and pub.tzinfo:
                pub = pub.astimezone(LOCAL_TZ)
            pub_str = pub.strftime("%d.%m.%Y") if pub else "—"

            sent_local = a.sent_at.astimezone(LOCAL_TZ) if a.sent_at and a.sent_at.tzinfo else None
            tag_values = _normalize_article_tags(a.tags)
            articles.append(
                {
                    "id": a.id,
                    "title": a.title,
                    "canonical_url": a.canonical_url,
                    "source_name": a.source_name,
                    "pub_date": pub_str,
                    "event_type": a.event_type,
                    "tags": tag_values,
                    "tag_value": tag_values[0] if tag_values else "",
                    "keep": a.keep,
                    "sent_at": a.sent_at,
                    "sent_label": sent_local.strftime("%d.%m") if sent_local else "",
                    "llm_summary": a.llm_summary or "",
                    "reason": a.llm_reason or "",
                    "processing_status": a.processing_status,
                    "decision_source": a.decision_source,
                    "fetch_error": a.fetch_error,
                    "classify_error": a.classify_error,
                }
            )

        if panel == "release":
            release_digest_date = digest_window[1].astimezone(LOCAL_TZ).strftime("%d.%m.%Y")
            release_sections = _build_release_sections(next_digest_rows)
            release_group_options = [
                {
                    "id": entry["id"],
                    "title": entry["title"],
                }
                for section in release_sections
                for entry in section["entries"]
            ]
            rejected_rows = db.execute(
                select(Article)
                .where(Article.fetched_at.isnot(None))
                .where(Article.sent_at.is_(None))
                .where(Article.keep.is_(False))
                .where(Article.published_at.isnot(None))
                .where(Article.published_at >= digest_window[0], Article.published_at < digest_window[1])
                .order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
                .limit(20)
            ).scalars().all()
            rejected_release_candidates = []
            for article in rejected_rows:
                pub = article.published_at or article.created_at
                if pub and pub.tzinfo:
                    pub = pub.astimezone(LOCAL_TZ)
                rejected_release_candidates.append(
                    {
                        "id": article.id,
                        "title": article.title,
                        "pub_date": pub.strftime("%d.%m.%Y") if pub else "—",
                        "reason": article.llm_reason or article.classify_error or article.fetch_error or "",
                        "summary": article.llm_summary or article.summary or "",
                        "event_type": article.event_type or "",
                        "tag_value": _primary_tag(article.tags) or "",
                        "group_parent_value": "",
                    }
                )
            digest_preview = {
                "title": "Текст следующего дайджеста",
                "digest_title": "Юридический дайджест",
                "digest_date_label": release_digest_date,
                "text": _format_digest_preview(next_digest_rows, "Юридический дайджест"),
                "html": _format_digest_preview_html(next_digest_rows, "Юридический дайджест"),
            }
        elif panel == "archive" and sent_digest_filter and archive_digest_rows:
            digest_preview = {
                "title": f"Текст дайджеста за {sent_digest_filter_label}",
                "subtitle": "Исторический текст выпуска для разбора и точечных исправлений по карточкам ниже.",
                "digest_title": f"Юридический дайджест за {sent_digest_filter_label}",
                "digest_date_label": sent_digest_filter_label,
                "text": _format_digest_preview(archive_digest_rows, f"Юридический дайджест за {sent_digest_filter_label}"),
                "html": _format_digest_preview_html(archive_digest_rows, f"Юридический дайджест за {sent_digest_filter_label}"),
            }

    panel_urls = {
        "release": _query_url(
            {"_path": _panel_base_path("release")},
            focus="next_digest",
            sent_digest="",
            keep="",
            source="",
            event_type="",
            status="",
            sent="",
            date_from="",
            date_to="",
            q="",
            errors_only="",
        ),
        "release_all": _query_url(
            {"_path": _panel_base_path("release")},
            focus="",
            sent_digest="",
            keep="",
            source="",
            event_type="",
            status="",
            sent="",
            date_from="",
            date_to="",
            q="",
            errors_only="",
        ),
        "delivery": _panel_base_path("delivery"),
        "archive": _query_url(
            {"_path": _panel_base_path("archive")},
            focus="",
            sent_digest="",
            keep="",
            source="",
            event_type="",
            status="",
            sent="",
            date_from="",
            date_to="",
            q="",
            errors_only="",
        ),
    }
    quick_urls = {
        "all": _query_url(base_args, keep="", sent="", errors_only="", source="", event_type="", status="", date_from="", date_to="", q="", focus="next_digest" if panel == "release" else focus_filter),
        "keep_true": _query_url(base_args, keep="1", sent="", errors_only=""),
        "keep_false": _query_url(base_args, keep="0", sent="", errors_only=""),
        "keep_null": _query_url(base_args, keep="null", sent="", errors_only=""),
        "unsent": _query_url(base_args, sent="0", keep="", errors_only=""),
        "sent": _query_url(base_args, sent="1", keep="", errors_only=""),
        "errors": _query_url(base_args, errors_only="1", keep="", sent=""),
    }
    quick_active = _resolve_quick_active(
        keep_filter,
        sent_filter,
        errors_only,
        source_filter,
        event_type_filter,
        status_filter,
        date_from,
        date_to,
        q,
    )
    if panel == "release":
        panel_heading = "Зона работы с предстоящим дайджестом"
        panel_intro = "Здесь живет все, что относится к ближайшему выпуску: состав, теги, типы и ручная доводка карточек перед отправкой."
        feed_title = "Карточки предстоящего выпуска"
        feed_subtitle = "Лента ниже посвящена именно будущему дайджесту. Она открывается сразу на кандидатах выпуска, а не на всей базе."
        all_pill_label = "Кандидаты выпуска"
        workspace_hint = "Открыты карточки, которые сейчас войдут в следующий выпуск"
        hero_notes = [
            f"кандидатов в выпуск: {len(next_digest_rows)}",
            f"нужно проверить: {next_digest_attention_count}",
            f"ручных решений: {next_digest_manual_count}",
        ]
        if focus_filter == "next_digest":
            workspace_hint = "Открыты карточки, которые сейчас войдут в следующий выпуск"
    elif panel == "delivery":
        panel_heading = "Зона статуса отправки дайджеста"
        panel_intro = "Здесь показан журнал отправок за все прошлые выпуски: какой дайджест собрался, ушел ли он, и если нет, то с какой ошибкой."
        feed_title = ""
        feed_subtitle = ""
        all_pill_label = ""
        workspace_hint = "Открыт журнал сборки и отправки выпусков"
        hero_notes = [
            f"последний статус: {latest_run['status_label'] if latest_run else 'нет данных'}",
            f"следующий выпуск: {len(next_digest_rows)} статей",
            f"архивных дат: {sent_digest_total}",
        ]
    else:
        panel_heading = "Зона архива и исправлений"
        panel_intro = "Прошлые выпуски, архив карточек и журнал ручных исправлений."
        feed_title = "Лента архива"
        feed_subtitle = "Здесь можно поднять старые карточки и поправить решение, тип или тег."
        all_pill_label = "Все архивные карточки"
        workspace_hint = "Открыт архив решений и прошлых выпусков"
        hero_notes = [
            f"архивных выпусков: {sent_digest_total}",
            f"исправлений в архиве: {review_archive}",
            f"всего ручных правок: {review_total}",
        ]
        if sent_digest_filter_label:
            workspace_hint = f"Открыт отправленный дайджест: {sent_digest_filter_label}"

    next_digest_feed_url = _query_url(
        {**base_args, "_path": _panel_base_path("release")},
        focus="next_digest",
        sent_digest="",
        keep="",
        sent="",
        date_from="",
        date_to="",
        q="",
        errors_only="",
    )

    return render_template_string(
        TEMPLATE,
        articles=articles,
        panel=panel,
        panel_heading=panel_heading,
        panel_intro=panel_intro,
        total=total,
        total_all=total_all,
        count_keep=count_keep,
        count_reject=count_reject,
        count_null=count_null,
        next_digest_total=len(next_digest_rows),
        next_digest_attention_count=next_digest_attention_count,
        next_digest_manual_count=next_digest_manual_count,
        next_digest_preview=_preview_items(next_digest_rows),
        digest_preview=digest_preview,
        release_sections=release_sections,
        release_group_options=release_group_options if panel == "release" else [],
        rejected_release_candidates=rejected_release_candidates if panel == "release" else [],
        digest_window_label=digest_window_label,
        latest_run=latest_run,
        digest_runs=digest_runs,
        failed_runs_count=failed_runs_count,
        sent_runs_count=sent_runs_count,
        sent_digest_total=sent_digest_total,
        sent_digest_groups=sent_digest_groups,
        sent_digest_filter=sent_digest_filter,
        sent_digest_filter_label=sent_digest_filter_label,
        review_stats={"total": review_total, "future": review_future, "archive": review_archive},
        page=page,
        total_pages=total_pages,
        page_range=_page_range(page, total_pages),
        page_url=lambda p: _page_url(base_args, p),
        sources=sources,
        event_types=event_types,
        statuses=statuses,
        workspace=workspace,
        focus_filter=focus_filter,
        keep_filter=keep_filter,
        source_filter=source_filter,
        event_type_filter=event_type_filter,
        status_filter=status_filter,
        sent_filter=sent_filter,
        date_from=date_from,
        date_to=date_to,
        q=q,
        errors_only=errors_only,
        current_path=_panel_base_path(panel),
        current_location=request.full_path[:-1] if request.full_path.endswith("?") else request.full_path,
        event_type_options=EVENT_TYPE_OPTIONS,
        tag_options=TAG_OPTIONS,
        panel_urls=panel_urls,
        workspace_hint=workspace_hint,
        feed_title=feed_title,
        feed_subtitle=feed_subtitle,
        all_pill_label=all_pill_label,
        next_digest_feed_url=next_digest_feed_url,
        quick_urls=quick_urls,
        quick_active=quick_active,
        reset_url=_query_url(base_args, keep="", source="", event_type="", status="", sent="", date_from="", date_to="", q="", errors_only=""),
    )


@app.route("/")
def index():
    return _render_panel("release")


@app.route("/delivery")
def delivery_panel():
    return _render_panel("delivery")


@app.route("/archive")
def archive_panel():
    return _render_panel("archive")


@app.route("/archive/reviews")
def archive_reviews_panel():
    with SessionLocal() as db:
        recent_reviews = []
        if inspect(db.bind).has_table("article_reviews"):
            recent_review_rows = db.execute(
                select(ArticleReview, Article.title)
                .join(Article, Article.id == ArticleReview.article_id)
                .order_by(ArticleReview.created_at.desc())
                .limit(100)
            ).all()
            for review, title in recent_review_rows:
                created_local = review.created_at.astimezone(LOCAL_TZ) if review.created_at and review.created_at.tzinfo else review.created_at
                recent_reviews.append(
                    {
                        "title": title,
                        "created_at": created_local.strftime("%d.%m %H:%M") if created_local else "—",
                        "action_label": _review_action_label(review.action),
                        "review_scope_label": _review_scope_label(review.review_scope),
                        "diff": _review_diff(review),
                    }
                )
    return render_template_string(REVIEWS_TEMPLATE, recent_reviews=recent_reviews)


if __name__ == "__main__":
    app.run(host=settings.web_host, port=settings.web_port, debug=False)
