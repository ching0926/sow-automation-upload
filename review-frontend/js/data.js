// SOW 審查頁面的後端 API client。
// 對應 backend/review.py 的 /api/review/cases/{token} 系列端點（token 是 HMAC-SHA256(job_code)，不直接暴露 job_code）。
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

function apiGetReviewCase(token) {
  return apiRequest('GET', `/api/review/cases/${token}`);
}

function apiSaveDraft(token, body) {
  return apiRequest('PUT', `/api/review/cases/${token}/draft`, body);
}

function apiSubmitReview(token, body) {
  return apiRequest('POST', `/api/review/cases/${token}/submit`, body);
}

function apiReturnToDri(token, body) {
  return apiRequest('POST', `/api/review/cases/${token}/return`, body);
}

function apiApprove(token, body) {
  return apiRequest('POST', `/api/review/cases/${token}/approve`, body);
}

function apiAddComment(token, body) {
  return apiRequest('POST', `/api/review/cases/${token}/comments`, body);
}

function apiUpdateComment(token, commentId, body) {
  return apiRequest('PUT', `/api/review/cases/${token}/comments/${commentId}`, body);
}

function apiDeleteComment(token, commentId, body) {
  return apiRequest('DELETE', `/api/review/cases/${token}/comments/${commentId}`, body);
}
