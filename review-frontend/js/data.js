// SOW 審查頁面 mock 資料。
// 這裡刻意跟 frontend/js/data.js 完全分開維護，欄位命名對齊
// frontend 的 detail.A/B/C 結構，方便之後接上真正的審查 API。
//
// 每個可編輯欄位存成 { original, current, savedAt }：
// - original：AI 原始萃取內容（DRI 送審後不再變動，做為對照基準）
// - current：目前內容（DRI 編輯/儲存後會更新）
// - savedAt：DRI 最近一次「儲存」這個欄位的時間，null 代表從未儲存過
// current !== original 時代表有異動，主管頁需顯示紅/綠 diff，否則顯示「無修改」。

function field(original, current, savedAt) {
  return { original, current: current === undefined ? original : current, savedAt: savedAt || null };
}

function baseDetail() {
  return {
    A: {
      industryBackground: field(
        '該客戶為國內大型基金代銷機構，旗下涵蓋多家投信合作的基金商品，每月須受理大量申購與轉換申請，長期面對主管機關對申購文件檢核與法遵留存的高標準要求。',
        undefined,
        '2025-11-04 10:20'
      ),
      challenge: field(
        '該機構每月需人工檢核逾百件基金申購文件，逐筆比對申請表、風險評估問卷與外部名單，平均每件耗時 4 小時，人力負擔重且容易因疲勞產生疏漏，一旦檢核疏漏可能觸及法遵風險。',
        '該機構每月需人工檢核大量基金申購文件，逐筆比對申請表、風險評估問卷與外部名單，平均每件耗時 4 小時，人力負擔重且容易因疲勞產生疏漏，一旦檢核疏漏可能觸及法遵風險。',
        '2025-11-04 10:21'
      ),
      solution: field(
        '透過 AI 自動擷取申請表資訊，自動比對外部資料並生成檢核報告，檢核時間降低 50%，提升準確性與合規性。',
        undefined,
        '2025-11-04 10:22'
      ),
      kpis: [
        { icon: '📉', value: field('50%'), label: field('檢核時間降低'), savedAt: '2025-11-04 10:23' },
        { icon: '📈', value: field('提升'), label: field('合規性與準確性'), savedAt: '2025-11-04 10:23' },
        { icon: '📉', value: field('降低'), label: field('人力負擔與疏漏風險'), savedAt: '2025-11-04 10:23' },
      ],
    },
    B: {
      owner: field('Christine Wang', undefined, '2025-11-04 10:20'),
      period: field('2025-11 ~ 2026-01', undefined, '2025-11-04 10:20'),
      teamSize: field('6', undefined, '2025-11-04 10:20'),
      manDays: field('45', undefined, '2025-11-04 10:20'),
      totalCost: field('NT$1,200,000', undefined, '2025-11-04 10:20'),
      deliverables: field(
        ['n8n workflow 樣板', '使用者操作手冊', '驗收測試報告'],
        undefined,
        '2025-11-04 10:20'
      ),
    },
    C: {
      coreFunctions: field(
        ['申請表資訊萃取', '資料自動比對', '檢核結果評分', '報告生成'],
        undefined,
        '2025-11-04 10:20'
      ),
      architecture: field(
        ['使用者', 'AI Agent Portal', 'n8n Workflow', 'Claude 3 (Bedrock)', '外部資料來源'],
        undefined,
        '2025-11-04 10:20'
      ),
      techStack: field(
        ['AWS EC2', 'Amazon Bedrock (Claude 3)', 'n8n Self Hosting'],
        undefined,
        '2025-11-04 10:20'
      ),
    },
  };
}

// DRI 進審查頁時的預設狀態：尚未送出，pill 顯示「DRI 審查中」。
const DRI_MOCK_CASE = {
  sowId: 'sow2k7r8',
  title: 'AI 基金商品檢核系統',
  industry: 'Financial Services',
  uploadedAt: '2025-11-03',
  driSubmittedAt: null,
  status: 'DRI_REVIEW',
  detail: baseDetail(),
};

// 主管進審查頁時的預設狀態：DRI 已送審，pill 顯示「主管審查中」。
const MANAGER_MOCK_CASE = {
  sowId: 'sow2k7r8',
  title: 'AI 基金商品檢核系統',
  industry: 'Financial Services',
  uploadedAt: '2025-11-03',
  driSubmittedAt: '2025-11-04 10:24',
  status: 'MANAGER_REVIEW',
  detail: baseDetail(),
};
