// SOW 審查頁面的後端 API client。
// 對應 backend/review.py 的 /api/review/cases/{sow_id} 系列端點。
// 回應資料每個可編輯欄位都已是 { original, current, savedAt } 形狀，
// 欄位命名對齊 frontend 的 detail.A/B/C 結構、也對齊本頁 FIELD_DEFS。

async function apiRequest(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  let payload = null;
  try {
    payload = await res.json();
  } catch (e) {
    // 沒有 body 或非 JSON，維持 payload = null
  }
  if (!res.ok) {
    const message = payload && payload.detail ? payload.detail : `請求失敗（${res.status}）`;
    throw new Error(message);
  }
  return payload;
}

function apiGetReviewCase(sowId) {
  return apiRequest('GET', `/api/review/cases/${sowId}`);
}

function apiSaveDraft(sowId, body) {
  return apiRequest('PUT', `/api/review/cases/${sowId}/draft`, body);
}

function apiSubmitReview(sowId, body) {
  return apiRequest('POST', `/api/review/cases/${sowId}/submit`, body);
}

function apiAddComment(sowId, body) {
  return apiRequest('POST', `/api/review/cases/${sowId}/comments`, body);
}

function apiReturnToDri(sowId, body) {
  return apiRequest('POST', `/api/review/cases/${sowId}/return`, body);
}

function apiApprove(sowId, body) {
  return apiRequest('POST', `/api/review/cases/${sowId}/approve`, body);
}
