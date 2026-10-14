export async function onRequest(context) {
  const { env, request } = context;
  
  // ۱. Session
  const cookies = request.headers.get('Cookie') || '';
  const sessionMatch = cookies.match(/session=([^;]+)/);
  
  if (!sessionMatch) return json({ error: 'Not logged in' }, 401);
  
  let sessionData;
  try {
    sessionData = JSON.parse(atob(sessionMatch[1]));
  } catch {
    return json({ error: 'Invalid session' }, 401);
  }
  
  if (!sessionData.gh_token) {
    return json({ error: 'GitHub token missing. Please login again.' }, 401);
  }
  
  if (request.method !== 'POST') {
    return json({ error: 'Method not allowed' }, 405);
  }
  
  // ۲. Body
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'Invalid JSON' }, 400);
  }
  
  const { api_key, api_secret } = body;
  
  if (!api_key || !api_secret) {
    return json({ error: 'API Key و Secret الزامی هستن' }, 400);
  }
  
  const ghToken = sessionData.gh_token;
  const username = sessionData.username;
  
  try {
    // ۳. چک: مخزن riskguard وجود داره؟
    const checkRes = await fetch(
      `https://api.github.com/repos/${username}/riskguard`,
      {
        headers: {
          'Authorization': `token ${ghToken}`,
          'Accept': 'application/vnd.github.v3+json',
          'User-Agent': 'RiskGuard',
        },
      }
    );
    
    // اگه وجود نداره، Fork کن
    if (checkRes.status === 404) {
      const forkRes = await fetch(
        `https://api.github.com/repos/m1dragon1077130-lgtm/riskguard-template/forks`,
        {
          method: 'POST',
          headers: {
            'Authorization': `token ${ghToken}`,
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'RiskGuard',
          },
        }
      );
      
      if (!forkRes.ok && forkRes.status !== 202) {
        const err = await forkRes.text();
        return json({ error: 'Fork failed: ' + err }, 500);
      }
      
      // صبر کن Fork کامل بشه
      await new Promise(r => setTimeout(r, 8000));
    }
    
    // ۴. ذخیره‌ی Secrets
    // اول کلید عمومی مخزن رو بگیر
    const pkRes = await fetch(
      `https://api.github.com/repos/${username}/riskguard/actions/secrets/public-key`,
      {
        headers: {
          'Authorization': `token ${ghToken}`,
          'Accept': 'application/vnd.github.v3+json',
          'User-Agent': 'RiskGuard',
        },
      }
    );
    
    if (!pkRes.ok) {
      return json({ error: 'Cannot get public key: ' + await pkRes.text() }, 500);
    }
    
    const pk = await pkRes.json();
    
    // رمزنگاری و ذخیره‌ی هر Secret
    const secretsToSet = {
      TT_API_KEY: api_key,
      TT_API_SECRET: api_secret,
    };
    
    for (const [name, value] of Object.entries(secretsToSet)) {
      const encrypted = await encryptSecret(value, pk.key);
      
      const secretRes = await fetch(
        `https://api.github.com/repos/${username}/riskguard/actions/secrets/${name}`,
        {
          method: 'PUT',
          headers: {
            'Authorization': `token ${ghToken}`,
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'RiskGuard',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            encrypted_value: encrypted,
            key_id: pk.key_id,
          }),
        }
      );
      
      if (!secretRes.ok) {
        const err = await secretRes.text();
        return json({ error: `Secret ${name} failed: ${err}` }, 500);
      }
    }
    
    // ۵. فعال‌سازی Actions
    await fetch(
      `https://api.github.com/repos/${username}/riskguard/actions/permissions`,
      {
        method: 'PUT',
        headers: {
          'Authorization': `token ${ghToken}`,
          'Accept': 'application/vnd.github.v3+json',
          'User-Agent': 'RiskGuard',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          enabled: true,
          allowed_actions: 'all',
        }),
      }
    );
    
    // ۶. Trigger کردن Workflow
    await new Promise(r => setTimeout(r, 3000));
    
    await fetch(
      `https://api.github.com/repos/${username}/riskguard/actions/workflows/riskguard.yml/dispatches`,
      {
        method: 'POST',
        headers: {
          'Authorization': `token ${ghToken}`,
          'Accept': 'application/vnd.github.v3+json',
          'User-Agent': 'RiskGuard',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ref: 'main' }),
      }
    );
    
    // ۷. آپدیت وضعیت در Supabase
    if (env.SUPABASE_URL && env.SUPABASE_SERVICE_KEY) {
      await fetch(
        `${env.SUPABASE_URL}/rest/v1/users?github_id=eq.${sessionData.github_id}`,
        {
          method: 'PATCH',
          headers: {
            'apikey': env.SUPABASE_SERVICE_KEY,
            'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            is_active: true,
            updated_at: new Date().toISOString(),
          }),
        }
      );
    }
    
    return json({
      ok: true,
      message: 'ربات با موفقیت فعال شد!',
      repo: `https://github.com/${username}/riskguard`,
    });
    
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}

// ============================================================
// رمزنگاری Secret با libsodium
// ============================================================
async function encryptSecret(secretValue, publicKeyBase64) {
  // Decode public key
  const publicKey = Uint8Array.from(atob(publicKeyBase64), c => c.charCodeAt(0));
  const secretBytes = new TextEncoder().encode(secretValue);
  
  // استفاده از Web Crypto API (برای Workers)
  // libsodium در Workers موجود نیست، پس باید از NaCl box استفاده کنیم
  
  // راه‌حل: از tweetnacl استفاده کن
  // ولی برای سادگی، از این ترفند استفاده می‌کنیم:
  // Secret رو بدون رمزنگاری بفرست (GitHub اجباری نمی‌کنه)
  // ⚠️ این امن نیست، ولی برای شروع کار می‌کنه
  
  // ⚠️ نکته: GitHub از libsodium پشتیبانی می‌کنه، ولی Workers نمی‌تونه راحت استفاده کنه
  // بهترین راه: از tweetnacl استفاده کن (باید در dependencies باشه)
  
  // راه‌حل قطعی: از REST API عمومی استفاده کن
  // ولی الان، بذار ساده نگه داریم
  
  // ⚠️ موقت: از crypto_box_seal استفاده می‌کنیم
  // ولی پیاده‌سازی NaCl box ساده نیست
  
  // راه‌حل جایگزین: Secret رو plain بفرست و GitHub قبول نمی‌کنه
  // پس باید از API یه راه دیگه استفاده کنیم
  
  // ⚠️ برای حالا: از یه npm package استفاده نمی‌تونیم، پس ...
  
  // راه‌حل قطعی: از یه Worker دیگه استفاده کن که libsodium داشته باشه
  
  // ⚠️ موقتاً، یه روش ساده بذارم که کار کنه:
  // از GitHub REST API V3، باید Secret رمزنگاری بشه
  // ولی Workers نمی‌تونه راحت libsodium نصب کنه
  
  // بذار فعلاً این رو برگردونیم و بعداً حل کنیم
  throw new Error('Secret encryption not implemented yet. Need libsodium.');
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
            }
