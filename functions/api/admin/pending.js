export async function onRequest(context) {
  const { env, request } = context;
  const url = new URL(request.url);
  const key = url.searchParams.get('key');
  
  if (key !== env.ADMIN_KEY) {
    return json({ error: 'Invalid admin key' }, 403);
  }
  
  try {
    const sbRes = await fetch(
      `${env.SUPABASE_URL}/rest/v1/users?referral_status=eq.pending&select=github_id,github_username,github_name,github_avatar,referral_requested_at&order=referral_requested_at.asc`,
      {
        headers: {
          'apikey': env.SUPABASE_SERVICE_KEY,
          'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
        },
      }
    );
    
    const users = await sbRes.json();
    
    return json({ ok: true, users });
    
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
