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
  
  if (request.method !== 'POST') {
    return json({ error: 'Method not allowed' }, 405);
  }
  
  try {
    // اول چک کن که کاربر روی لینک کلیک کرده
    const checkRes = await fetch(
      `${env.SUPABASE_URL}/rest/v1/users?github_id=eq.${sessionData.github_id}&select=referral_clicked,referral_confirmed`,
      {
        headers: {
          'apikey': env.SUPABASE_SERVICE_KEY,
          'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        },
      }
    );
    
    const users = await checkRes.json();
    
    if (!users || users.length === 0) {
      return json({ error: 'User not found' }, 404);
    }
    
    const user = users[0];
    
    if (!user.referral_clicked) {
      return json({ error: 'ابتدا باید روی لینک رفرال کلیک کنی' }, 400);
    }
    
    if (user.referral_confirmed) {
      return json({ error: 'قبلاً تخفیف گرفتی' }, 400);
    }
    
    // تایید تخفیف
    const sbRes = await fetch(
      `${env.SUPABASE_URL}/rest/v1/users?github_id=eq.${sessionData.github_id}`,
      {
        method: 'PATCH',
        headers: {
          'apikey': env.SUPABASE_SERVICE_KEY,
          'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
          'Content-Type': 'application/json',
          'Prefer': 'return=minimal',
        },
        body: JSON.stringify({
          referral_confirmed: true,
          referral_confirmed_at: new Date().toISOString(),
          discount_percent: 50,
        }),
      }
    );
    
    if (!sbRes.ok) {
      const errText = await sbRes.text();
      return json({ error: 'DB error: ' + errText }, 500);
    }
    
    return json({ ok: true, discount: 50 });
    
  } catch (err) {
    return json({ error: err.message }, 500);
  }
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
