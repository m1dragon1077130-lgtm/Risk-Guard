export async function onRequest(context) {
  const { env, request } = context;
  
  const cookies = request.headers.get('Cookie') || '';
  const sessionMatch = cookies.match(/session=([^;]+)/);
  
  if (!sessionMatch) return json({ error: 'Not logged in' }, 401);
  
  let sessionData;
  try { sessionData = JSON.parse(atob(sessionMatch[1])); } catch { return json({ error: 'Invalid session' }, 401); }
  
  if (!sessionData.gh_token) return json({ error: 'GitHub token missing' }, 401);
  if (request.method !== 'POST') return json({ error: 'Method not allowed' }, 405);
  
  let body;
  try { body = await request.json(); } catch { return json({ error: 'Invalid JSON' }, 400); }
  
  const { api_key, api_secret } = body;
  if (!api_key || !api_secret) return json({ error: 'API Key و Secret الزامی هستن' }, 400);
  
  const ghToken = sessionData.gh_token;
  const username = sessionData.username;
  const repo = `${username}/riskguard`;
  
  try {
    // ۱. چک: مخزن riskguard وجود داره؟
    let checkRes = await ghFetch(`https://api.github.com/repos/${repo}`, ghToken);
    
    if (checkRes.status === 404) {
      // Fork کن (با اجبار اسم riskguard)
      const forkRes = await ghFetch(
        `https://api.github.com/repos/m1dragon1077130-lgtm/riskguard-template/forks`,
        ghToken,
        'POST',
        { name: "riskguard" }
      );
      
      if (!forkRes.ok && forkRes.status !== 202) {
        return json({ error: 'Fork failed: ' + await forkRes.text() }, 500);
      }
      
      // ۱۵ ثانیه صبر میکنیم تا گیت‌هاب فایل‌ها رو کپی کنه
      await new Promise(r => setTimeout(r, 15000));
    }
    
    // ۲. آپدیت config.json
    let configRes = await ghFetch(`https://api.github.com/repos/${repo}/contents/config.json`, ghToken);
    
    if (!configRes.ok) {
      await new Promise(r => setTimeout(r, 5000));
      configRes = await ghFetch(`https://api.github.com/repos/${repo}/contents/config.json`, ghToken);
    }
    
    let sha = null;
    let currentConfig = {};
    
    if (configRes.ok) {
      const configData = await configRes.json();
      sha = configData.sha;
      try {
        const decoded = decodeURIComponent(escape(atob(configData.content)));
        currentConfig = JSON.parse(decoded);
      } catch (e) {}
    }
    
    const newConfig = {
      ...currentConfig,
      tt_api_key: api_key,
      tt_api_secret: api_secret,
    };
    
    const configStr = JSON.stringify(newConfig, null, 2);
    const configB64 = btoa(unescape(encodeURIComponent(configStr)));
    
    const updateConfigBody = { message: 'Update config with API keys', content: configB64 };
    if (sha) updateConfigBody.sha = sha;
    
    const updateConfigRes = await ghFetch(`https://api.github.com/repos/${repo}/contents/config.json`, ghToken, 'PUT', updateConfigBody);
    
    if (!updateConfigRes.ok) {
      return json({ error: 'Config update failed: ' + await updateConfigRes.text() }, 500);
    }
    
    // ۳. فعال‌سازی Actions
    await ghFetch(`https://api.github.com/repos/${repo}/actions/permissions`, ghToken, 'PUT', { enabled: true, allowed_actions: 'all' });
    
    // ۴. Trigger کردن Workflow (با اسم دقیق فایل riskguard.yml)
    await new Promise(r => setTimeout(r, 3000));
    await ghFetch(`https://api.github.com/repos/${repo}/actions/workflows/riskguard.yml/dispatches`, ghToken, 'POST', { ref: 'main' });
    
    // ۵. آپدیت Supabase
    if (env.SUPABASE_URL && env.SUPABASE_SERVICE_KEY) {
      await fetch(`${env.SUPABASE_URL}/rest/v1/users?github_id=eq.${sessionData.github_id}`, {
        method: 'PATCH',
        headers: { 
            'apikey': env.SUPABASE_SERVICE_KEY, 
            'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`, 
            'Content-Type': 'application/json' 
        },
        body: JSON.stringify({ 
            is_active: true, 
            has_paid: true 
        }),
      });
    }
    
    return json({ ok: true, message: 'ربات فعال شد!' });
    
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}

function ghFetch(url, token, method = 'GET', body = null) {
  const options = { 
    method, 
    headers: { 
      'Authorization': `token ${token}`, 
      'Accept': 'application/vnd.github.v3+json', 
      'User-Agent': 'RiskGuard' 
    } 
  };
  if (body) { 
    options.headers['Content-Type'] = 'application/json'; 
    options.body = JSON.stringify(body); 
  }
  return fetch(url, options);
}

function json(data, status = 200) { 
  return new Response(JSON.stringify(data), { 
    status, 
    headers: { 'Content-Type': 'application/json' } 
  }); 
}
