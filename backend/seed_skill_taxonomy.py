"""
資料填充腳本：把根目錄 industry_category_skills.md「二、技能分類與技術對照」整份表格
（領域 Domain → 分類 Category → 技能 Skill）灌進 tag_definition，供案例平台 SA 角色的
category/skill 篩選使用（GET /api/skill-taxonomy）。

用 (tag_category, tag_name) 既有的複合唯一約束做 UPSERT：新技能新增一筆
（tag_category='TECH_PLATFORM'），跟既有標籤撞名的（目前是 Python、Amazon Bedrock）
直接更新那一筆，補上 domain/category/skill_name，不會造成重複標籤。

這支腳本只負責參考表資料本身，不會去比對/修改任何案例現有掛的標籤關聯
（sow_tag_relation），也不會處理 industry_category_skills.md 裡「一、產業類別」那份清單。

可重複執行。
"""
from sqlalchemy import text

from db import SessionLocal

# domain -> category -> [skill, ...]，內容逐字對應 industry_category_skills.md 的表格
TAXONOMY = {
    "開發與實作 - 系統開發 (Development & Implementation - System Development)": {
        "後端開發 (Back-End Development)": ["Python", "Java", "Node.js"],
        "前端開發 (Front-End Development)": ["React", "TypeScript", "Vue.js", "Next.js"],
        "資料工程 (Data Engineering)": ["Apache Kafka", "Apache Spark", "dbt", "Apache Airflow"],
        "機器學習 (Machine Learning)": ["PyTorch", "scikit-learn", "MLflow", "XGBoost"],
        "生成式 AI (Generative AI)": ["LangChain", "LlamaIndex", "Amazon Bedrock", "Hugging Face"],
        "資料庫管理與設計 (Database Management & Design)": ["PostgreSQL", "MySQL", "MongoDB", "Redis"],
        "測試 (Testing)": ["pytest", "Jest", "Cypress", "k6"],
    },
    "開發與實作 - 系統整合 (Development & Implementation - System Integration)": {
        "系統整合 (System Integration)": ["MuleSoft", "MQTT", "OPC-UA", "Apache Camel"],
    },
    "交付與維運 (Delivery & Operations)": {
        "雲端基礎設施 (Cloud Infrastructure)": ["Terraform", "Docker", "Kubernetes", "AWS CloudFormation"],
        "雲端遷移 (Cloud Migration)": ["AWS Migration Hub", "AWS DMS", "Azure Migrate"],
        "DevOps 工程 (DevOps Engineering)": ["GitHub Actions", "ArgoCD", "Prometheus", "Datadog"],
        "資訊安全 (Information Security)": ["AWS GuardDuty", "Burp Suite", "Nessus", "AWS WAF"],
    },
    "策略與架構 (Strategy & Architecture)": {
        "解決方案架構 (Solution Architecture)": [
            "AWS Well-Architected Tool",
            "TOGAF",
            "Lucidchart",
            "Draw.io",
        ],
        "顧問諮詢 (Consulting)": [
            "數位轉型規劃 (Digital Transformation Planning)",
            "POC 執行 (POC Execution)",
            "工作坊引導 (Workshop Facilitation)",
        ],
    },
    "專案與產品管理 (Project & Product Management)": {
        "專案管理 (Project Management)": ["Scrum", "PMP", "風險管理 (Risk Management)"],
        "產品管理 (Product Management)": [
            "A/B Testing",
            "競品分析 (Competitive Analysis)",
            "PRDs 撰寫 (PRD Writing)",
        ],
    },
    "企業應用系統 (Enterprise Application Systems)": {
        "SAP": ["SAP FI", "SAP MM", "SAP Fiori", "SAP Basis 系統管理"],
        "Salesforce": [
            "Marketing Cloud",
            "Sales Cloud",
            "Lightning Web Components",
            "Salesforce Flow 系統管理",
        ],
        "Oracle": ["Oracle SCM", "Oracle Fusion HCM", "Oracle APEX", "Oracle DBA"],
    },
    "其他技能 (Other Skills)": {
        "綜合與通用技能 (Other Skills)": ["Supply Chain Management", "Risk Assessment", "SQL", "Tableau"],
    },
}


def main():
    db = SessionLocal()
    try:
        inserted_or_updated = 0
        for domain, categories in TAXONOMY.items():
            for category, skills in categories.items():
                for skill in skills:
                    db.execute(
                        text(
                            """
                            INSERT INTO tag_definition (tag_category, tag_name, is_active, domain, category, skill_name)
                            VALUES ('TECH_PLATFORM', :skill, true, :domain, :category, :skill)
                            ON CONFLICT (tag_category, tag_name) DO UPDATE
                            SET domain = EXCLUDED.domain,
                                category = EXCLUDED.category,
                                skill_name = EXCLUDED.skill_name
                            """
                        ),
                        {"skill": skill, "domain": domain, "category": category},
                    )
                    inserted_or_updated += 1
        db.commit()
        print(f"完成：{inserted_or_updated} 筆技能已寫入 tag_definition（新增或更新）。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
