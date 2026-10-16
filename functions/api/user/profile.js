export async function onRequest(context) {
  const { env, request } = context;
  
  const cookies = request.headers.get('Cookie') || '';
  const sessionMatch = cookies.match(/session=([^;]+)/);
  
  if (!sessionMatch) {
    return json({ error: 'Not logged in' }, 401);
  }
  
  let sessionData;
  try {
    sessionData = JSON.parse(atob(sessionMatch[1]));
  } catch {
    return json({ error: 'Invalid session' }, 401);
  }
  
  if (!env.SUPABASE_URL || !env.SUPABASE_SERVICE_KEY) {
    return json({ error: 'Server config error' }, 500);
  }
  
  try {
    const sbRes = await fetch(
      `${env.SUPABASE_URL}/rest/v1/users?github_id=eq.${sessionData.github_id}&select=*`,
      {
        headers: {
          'apikey': env.SUPABASE_SERVICE_KEY,
          'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        },
      }
    );
    
    if (!sbRes.ok) {
      return json({ error: 'DB error: ' + sbRes.status }, 500);
    }
    
    const users = await sbRes.json();
    
    if (!users || users.length === 0) {
      return json({ error: 'User not found' }, 404);
    }
    
    const user = users[0];
    
    return json({
      ok: true,
      user: {
        github_id: user.github_id,
        username: user.github_username,
        name: user.github_name,
        avatar: user.github_avatar,
        has_paid: user.has_paid || false,
        is_active: user.is_active || false,
        config: user.config,
        referral_clicked: user.referral_clicked || false,
        referral_status: user.referral_status || 'none',
        created_at: user.created_at,
      },
    });
    
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
