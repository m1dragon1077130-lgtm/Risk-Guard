import nacl from '../_lib/nacl.js';

export async function onRequest(context) {
  const { env, request } = context;
  
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
    return json({ error: 'GitHub token missing' }, 401);
  }
  
  if (request.method !== 'POST') {
    return json({ error: 'Method not allowed' }, 405);
  }
  
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
    // ۱. چک: مخزن riskguard وجود داره؟
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
    
    if (checkRes.status === 404) {
      // Fork کن
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
      
      await new Promise(r => setTimeout(r, 8000));
    }
    
    // ۲. کلید عمومی مخزن رو بگیر
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
    
    // ۳. رمزنگاری و ذخیره‌ی هر Secret
    const secretsToSet = {
      TT_API_KEY: api_key,
      TT_API_SECRET: api_secret,
    };
    
    for (const [name, value] of Object.entries(secretsToSet)) {
      const encrypted = encryptSecret(value, pk.key);
      
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
    
    // ۴. فعال‌سازی Actions
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
    
    // ۵. Trigger کردن Workflow
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
    
    // ۶. آپدیت وضعیت در Supabase
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
// رمزنگاری Secret با tweetnacl
// ============================================================
function encryptSecret(secretValue, publicKeyBase64) {
  const publicKey = base64ToUint8(publicKeyBase64);
  const message = new TextEncoder().encode(secretValue);
  
  const ephemeralKeyPair = nacl.box.keyPair();
  const nonce = nacl.randomBytes(24);
  
  const encrypted = nacl.box(message, nonce, publicKey, ephemeralKeyPair.secretKey);
  
  const sealedBox = new Uint8Array(ephemeralKeyPair.publicKey.length + encrypted.length);
  sealedBox.set(ephemeralKeyPair.publicKey, 0);
  sealedBox.set(encrypted, ephemeralKeyPair.publicKey.length);
  
  return uint8ToBase64(sealedBox);
}


function base64ToUint8(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}


function uint8ToBase64(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}


function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
    }
