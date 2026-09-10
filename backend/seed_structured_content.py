"""
一次性腳本：把 4 筆現有 sow_document 對應的結構化內容灌進 sow_structured_content。
內容依原始 SOW markdown 摘要改寫（非憑空捏造），格式符合 json.txt 的
SOW_ANALYSIS_TOOL schema 中 customer_context / project_planning / technical_design 三個區塊。
可重複執行：每次先刪除該 sow_id 既有的 structured content 再重新寫入。
"""
import json

from sqlalchemy import text

from db import SessionLocal

STRUCTURED_CONTENT = {
    1: {
        "customer_context": {
            "industry_background": "某大型銀行信託處，每月處理約 10 檔基金商品申請案，長期面對主管機關對申購文件檢核與法遵留存的高標準要求。",
            "challenge": "審核專員需從申請表擷取資訊，並至 4 個外部網站（基金觀測站、投信投顧公會、晨星、基金公司官網）查詢資料，進行 20 項資訊正確性檢核，每檔商品約需 4 小時人工處理，5 位同仁每月共投入 40 小時，每月額外支付 20,000 元加班費（年度 240,000 元），且人工檢核流程耗時易出錯、缺乏標準化、稽核軌跡不完整。",
            "solution": "建置 AI Agent 基金商品檢核系統，透過智能申請表辨識自動萃取基金名稱、類型、投資標的、風險等級等關鍵資訊，比對外部資料並自動生成檢核報告，全面提升檢核效率與準確性。",
            "kpis": [
                {"icon": "⏱️", "value": "50%", "label": "檢核時間縮短"},
                {"icon": "🕑", "value": "20hr", "label": "每月省人力"},
                {"icon": "💰", "value": "NT$240K", "label": "年節省成本"},
                {"icon": "✅", "value": "Audit Trail", "label": "建立稽核軌跡，符合監理要求"},
            ],
        },
        "project_planning": {
            "owner": "ECV 專案經理",
            "team_size": 6,
            "period": "2026/01/05 - 2026/03/13",
            "man_days": 48,
            "total_cost": "NT$ 1,920,000",
            "deliverables": ["n8n workflow 樣板", "使用者操作手冊", "驗收測試報告"],
        },
        "technical_design": {
            "core_functions": ["智能申請表辨識", "資料自動比對", "檢核結果評分", "報告生成", "通知與提醒"],
            "architecture_nodes": [
                "使用者（申請文件上傳、檢核結果查詢、報告下載/追蹤）",
                "AI Agent Portal（文件結構解析、欄位比對邏輯）",
                "n8n Workflow（流程 orchestration、任務調度、資料轉換）",
                "Claude 3 (Bedrock)（資訊萃取、資料比對、檢核結果評分、摘要生成）",
                "外部資料來源（基金資料庫、投信投顧公會、風險名單、基金公司網站）",
            ],
            "tech_stack": ["AWS EC2", "Amazon Bedrock (Claude 3)", "n8n Self Hosting", "NLP", "RESTful API"],
        },
    },
    2: {
        "customer_context": {
            "industry_background": "某大型醫院婦產科部門，每月服務上百位孕產婦，透過 LINE 提供病患衛教諮詢服務。",
            "challenge": "每日透過 LINE 接收的病患諮詢訊息最高達 45 則，行政助理需逐一人工回覆；孕婦在產檢空窗期間常因出血、頭痛、水腫、血壓異常等生理症狀感到焦慮而反覆詢問，回覆品質高度仰賴個人經驗、不同助理間不一致，且大量訊息中難以快速識別高風險緊急狀況，也缺乏標準化的醫療衛教資訊。",
            "solution": "打造 LINE AI 客服輔助系統，採用人機協作（Human-in-the-loop）模式：AI 根據 RAG 知識庫生成醫療衛教回覆草稿，統一由醫護人員審核後才發送，不自動直接回覆病患，確保回覆品質與安全性。",
            "kpis": [
                {"icon": "⏱️", "value": "40%", "label": "回覆草稿產出時間縮短"},
                {"icon": "🕑", "value": "10hr", "label": "每月省人力"},
                {"icon": "✅", "value": "Human-in-the-loop", "label": "AI 草稿皆經醫護審核才發送"},
                {"icon": "🔒", "value": "ap-east-2", "label": "資料僅留在台北 Region，不用於模型再訓練"},
            ],
        },
        "project_planning": {
            "owner": "ECV DRI",
            "team_size": 5,
            "period": "2025/12/01 - 2026/02/06",
            "man_days": 35,
            "total_cost": "NT$ 1,400,000",
            "deliverables": ["LINE AI Agent 系統上線", "使用者操作手冊", "驗收測試報告"],
        },
        "technical_design": {
            "core_functions": ["智慧回覆草稿生成", "RAG 醫療衛教知識庫檢索", "高風險症狀識別", "人工審核派送流程"],
            "architecture_nodes": [
                "LINE Messaging API（病患端通訊介面，Webhook 接收/回傳訊息）",
                "CloudFront + AWS Lambda（Webhook 事件處理，Serverless 入口點）",
                "Amazon Bedrock + RAG 知識庫（LLM 推論生成醫療衛教回覆草稿）",
                "醫護人員審核介面（草稿審核後發送）",
            ],
            "tech_stack": ["AWS Lambda", "Amazon S3", "Amazon Bedrock", "RAG", "Serverless", "CloudFront", "DynamoDB", "AWS IAM"],
        },
    },
    12: {
        "customer_context": {
            "industry_background": "內部營運系統優化案，適用於具備複雜訂單管理與財務請款流程的企業，原有訂單管理系統僅支援整張訂單統一請款方式。",
            "challenge": "企業每月需手動處理 230-250 張訂單、耗費約 12 人天進行請款調整，因無法針對訂單中不同商品分別設定請款規則，導致人工作業負擔重、容易產生疏漏影響財務資料正確性，也無法快速回應客戶對彈性付款方式的需求。",
            "solution": "開發「訂單項目層級請款計畫管理系統」，支援針對訂單中每個商品項目分別設定獨立的請款計畫（時間、金額、週期），並以智慧規則引擎依商品類型自動判斷應採用的請款方式，減少人工調整。",
            "kpis": [
                {"icon": "⏱️", "value": "12人天/月", "label": "原人工請款調整工時"},
                {"icon": "📦", "value": "230-250張", "label": "每月處理訂單數"},
                {"icon": "✅", "value": "By Item / By Order", "label": "支援雙模式請款計畫"},
                {"icon": "🔗", "value": "OMS ↔ ERP", "label": "資料一致性提升"},
            ],
        },
        "project_planning": {
            "owner": "DX (Digital Transformation) 部門",
            "team_size": 4,
            "period": "中型專案（82.25 人天）",
            "man_days": 82,
            "total_cost": "內部專案，以人天計價（未列外部報價）",
            "deliverables": ["OMS Billing Plan 功能上線（By Item / By Order）", "SAP RFC 整合介面", "使用者操作手冊"],
        },
        "technical_design": {
            "core_functions": [
                "Item 層級 Billing Plan CRUD",
                "單一層級限制邏輯（By Order 或 By Item 不可並存）",
                "依料號首碼自動判斷請款規則",
                "OMS 與 SAP ERP 雙向資料同步",
            ],
            "architecture_nodes": [
                "前端層：OMS UI（Billing Plan 建立類型下拉選單）",
                "應用層：Python 後端 API（Billing Plan CRUD）",
                "資料層：RDS PostgreSQL（Billing Plan 配置與狀態）",
                "整合層：RFC 介面（與 SAP ERP 雙向資料交換）",
            ],
            "tech_stack": ["Python", "RDS PostgreSQL", "RFC", "SAP", "ERP"],
        },
    },
    29: {
        "customer_context": {
            "industry_background": "某科技服務公司的內部數位轉型案例，服務對象為專案管理辦公室（PMO）部門，屬跨國企業，具備多個分公司與區域中心。",
            "challenge": "父子專案的客戶名稱、銷售人員、機會階段等資訊需手動維護，容易造成主專案與子專案資料不同步、報表不一致；報表缺少專案費用（Expense）欄位，無法即時掌握外包費用與成本結構；也缺乏專案備註欄位記錄特殊情況，可追溯性不足。",
            "solution": "透過自動化資料整合技術，串接 AHG System 主資料來源，以 Power Automate 定期同步父子專案關聯、新增 Expense Subtotal 與 Comment 欄位至 RDS PostgreSQL，並完成 ECV、CRS、ECR 三個實體環境的部署，解決資料一致性與財務追蹤問題。",
            "kpis": [
                {"icon": "⏱️", "value": "2,253 小時", "label": "年度節省手動作業時間"},
                {"icon": "💰", "value": "US$78,855", "label": "年度節省金額"},
                {"icon": "📈", "value": "415%", "label": "第一年 ROI"},
                {"icon": "🌐", "value": "ECV / CRS / ECR", "label": "三環境部署完成"},
            ],
        },
        "project_planning": {
            "owner": "SDX 部門",
            "team_size": 3,
            "period": "PMO 部門發起，SDX 部門承接",
            "man_days": 15,
            "total_cost": "US$78,855 年度節省金額（投資回報導向，非開發報價）",
            "deliverables": ["父子專案資料一致性修正", "Expense Subtotal 欄位上線", "Comment 欄位上線", "ECV/CRS/ECR 三環境部署"],
        },
        "technical_design": {
            "core_functions": ["父子專案資料一致性同步", "Expense Subtotal 欄位新增", "Comment 備註欄位新增", "三環境（ECV/CRS/ECR）部署"],
            "architecture_nodes": [
                "資料來源層：AHG System（Main Code / Sub Code 關聯）",
                "資料整合層：Power Automate（定期自動化同步）",
                "資料儲存層：RDS PostgreSQL（核心資料儲存）",
            ],
            "tech_stack": ["RDS PostgreSQL", "Power Automate", "AHG System"],
        },
    },
}


def main():
    db = SessionLocal()
    try:
        for sow_id, content in STRUCTURED_CONTENT.items():
            db.execute(text("DELETE FROM sow_structured_content WHERE sow_id = :sow_id"), {"sow_id": sow_id})
            db.execute(
                text(
                    """
                    INSERT INTO sow_structured_content (sow_id, version, customer_context, project_planning, technical_design)
                    VALUES (:sow_id, 1, CAST(:cc AS JSONB), CAST(:pp AS JSONB), CAST(:td AS JSONB))
                    """
                ),
                {
                    "sow_id": sow_id,
                    "cc": json.dumps(content["customer_context"], ensure_ascii=False),
                    "pp": json.dumps(content["project_planning"], ensure_ascii=False),
                    "td": json.dumps(content["technical_design"], ensure_ascii=False),
                },
            )
        db.commit()
        print(f"Seeded sow_structured_content for sow_id={list(STRUCTURED_CONTENT.keys())}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
