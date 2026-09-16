// Mock 資料：篩選代碼標籤字典（雙語）＋ 16 筆案例資料
// 每筆案例的 detail = { A, B, C }，前端依角色累加規則（見 app.js ROLE_SECTIONS）決定顯示哪些區塊，
// 而不是替每個角色各寫一份窄化內容 —— 這是修正參考圖 ui_v1.png 中「PM 只顯示 B、SA 只顯示 C」錯誤的核心。

const LABELS = {
  service: {
    ai_genai: { zh: 'AI / GenAI', en: 'AI / GenAI', color: 'purple' },
    automation: { zh: '自動化', en: 'Automation', color: 'purple' },
    data_analytics: { zh: '數據分析', en: 'Data Analytics', color: 'purple' },
    security: { zh: '資安防護', en: 'Security', color: 'purple' },
  },
  usecase: {
    doc_processing: { zh: '文件處理', en: 'Document Processing', color: 'amber' },
    nlp: { zh: 'NLP', en: 'NLP', color: 'amber' },
    ocr: { zh: 'OCR', en: 'OCR', color: 'amber' },
    data_insight: { zh: '數據分析', en: 'Data Analysis', color: 'amber' },
    fraud_detect: { zh: '稽核偵測', en: 'Anomaly Detection', color: 'amber' },
    demand_forecast: { zh: '需求預測', en: 'Demand Forecasting', color: 'amber' },
    conversation: { zh: '客服對話', en: 'Conversational AI', color: 'amber' },
    equipment_monitor: { zh: '設備監控', en: 'Equipment Monitoring', color: 'amber' },
    route_optimize: { zh: '路線優化', en: 'Route Optimization', color: 'amber' },
  },
  skill: {
    aws: { zh: 'AWS', en: 'AWS', color: 'blue' },
    claude: { zh: 'Claude', en: 'Claude', color: 'orange' },
    n8n: { zh: 'n8n', en: 'n8n', color: 'teal' },
    python: { zh: 'Python', en: 'Python', color: 'indigo' },
    bedrock: { zh: 'Bedrock', en: 'Bedrock', color: 'orange' },
    restapi: { zh: 'RESTful API', en: 'RESTful API', color: 'gray' },
  },
  role: {
    PM: { zh: 'PM', en: 'PM' },
    RD: { zh: 'RD', en: 'RD' },
    QC: { zh: 'QC', en: 'QC' },
    SA: { zh: 'SA', en: 'SA' },
    UIUX: { zh: 'UI/UX', en: 'UI/UX' },
  },
  wbsPhase: {
    kickoff: { zh: '專案啟動', en: 'Kickoff' },
    analysis: { zh: '需求訪談', en: 'Requirement Analysis' },
    design_dev: { zh: '設計與開發', en: 'Design & Development' },
    testing: { zh: '測試與修復', en: 'Testing & Fixes' },
    uat: { zh: '驗收上線', en: 'UAT & Go-live' },
    handover: { zh: '結案交付', en: 'Handover' },
  },
  deliverable: {
    workflow_template: { zh: 'n8n workflow 樣板', en: 'n8n workflow template' },
    user_manual: { zh: '使用者操作手冊', en: 'User operation manual' },
    uat_report: { zh: '驗收測試報告', en: 'UAT report' },
    source_repo: { zh: '原始碼交接', en: 'Source code handover' },
    training_session: { zh: '教育訓練場次', en: 'Training session' },
    ops_manual: { zh: '維運手冊', en: 'Operations manual' },
  },
  archNode: {
    user: { zh: '使用者', en: 'User' },
    ai_portal: { zh: 'AI Agent Portal', en: 'AI Agent Portal' },
    n8n_workflow: { zh: 'n8n Workflow', en: 'n8n Workflow' },
    claude_bedrock: { zh: 'Claude 3 (Bedrock)', en: 'Claude 3 (Bedrock)' },
    external_sources: { zh: '外部資料來源', en: 'External Data Sources' },
  },
  archNodeDetail: {
    user: { zh: ['申請文件上傳', '檢核結果查詢', '報告下載/追蹤'], en: ['Upload application docs', 'Query review results', 'Download / track reports'] },
    ai_portal: { zh: ['文件結構解析', '欄位比對邏輯'], en: ['Document structure parsing', 'Field matching logic'] },
    n8n_workflow: { zh: ['流程 orchestration', '任務調度', '資料轉換'], en: ['Process orchestration', 'Task scheduling', 'Data transformation'] },
    claude_bedrock: { zh: ['資訊萃取', '資料比對', '檢核結果評分', '摘要生成'], en: ['Information extraction', 'Data matching', 'Review scoring', 'Summary generation'] },
    external_sources: { zh: ['基金資料庫', '投信投顧公會', '風險名單', '基金公司網站'], en: ['Fund database', 'SITCA registry', 'Risk watchlist', 'Fund company site'] },
  },
  techstack: {
    aws_ec2: 'AWS EC2',
    bedrock_claude3: 'Amazon Bedrock (Claude 3)',
    n8n_self_hosting: 'n8n Self Hosting',
    nlp: 'NLP',
    python: 'Python',
    restful_api: 'RESTful API',
    aws_lambda: 'AWS Lambda',
    aws_s3: 'Amazon S3',
    textract: 'Amazon Textract',
    sagemaker: 'Amazon SageMaker',
    aws_rds: 'Amazon RDS',
    quicksight: 'Amazon QuickSight',
  },
  corefunction: {
    form_extraction: { zh: '申請表資訊萃取', en: 'Application form extraction' },
    data_matching: { zh: '資料自動比對', en: 'Automated data matching' },
    risk_scoring: { zh: '檢核結果評分', en: 'Review scoring' },
    report_gen: { zh: '報告生成', en: 'Report generation' },
    notification: { zh: '通知與提醒', en: 'Notification & alerts' },
    dashboard: { zh: '儀表板視覺化', en: 'Dashboard visualization' },
    anomaly_alert: { zh: '異常即時警示', en: 'Real-time anomaly alerts' },
  },
  status: {
    planning: { zh: '規劃中', en: 'Planning' },
    in_progress: { zh: '執行中', en: 'In Progress' },
    completed: { zh: '已結案', en: 'Completed' },
  },
};

function L(dict, code, lang) {
  return LABELS[dict][code] ? LABELS[dict][code][lang] : code;
}

// 真實案例資料改由 /api/cases 提供（見 backend/app.py），不再寫死於此檔。
let CASES = [];

async function loadCases() {
  const res = await fetch('/api/cases');
  if (!res.ok) throw new Error(`Failed to load /api/cases: ${res.status}`);
  CASES = await res.json();
}

// SA 角色的 category/skill 篩選參考表（來自 tag_definition，見 backend/app.py 的 GET /api/skill-taxonomy），
// 形狀是 { category: [skill_name, ...] }，跟案例實際資料無關，是完整的技能分類對照表。
let SKILL_TAXONOMY = {};

async function loadSkillTaxonomy() {
  const res = await fetch('/api/skill-taxonomy');
  if (!res.ok) throw new Error(`Failed to load /api/skill-taxonomy: ${res.status}`);
  SKILL_TAXONOMY = await res.json();
}

