export async function onRequest(context) {
  const { env, request } = context;
  
  if (request.method !== 'POST') {
    return json({ error: 'Method not allowed' }, 405);
  }
  
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'Invalid JSON' }, 400);
  }
  
  const { key, github_id, action } = body;
  
  if (key !== env.ADMIN_KEY) {
    return json({ error: 'Invalid admin key' }, 403);
  }
  
  if (!github_id || !['approve', 'reject'].includes(action)) {
    return json({ error: 'Invalid params' }, 400);
  }
  
  try {
    const status = action === 'approve' ? 'approved' : 'rejected';
    
    const sbRes = await fetch(
      `${env.SUPABASE_URL}/rest/v1/users?github_id=eq.${github_id}`,
      {
        method: 'PATCH',
        headers: {
          'apikey': env.SUPABASE_SERVICE_KEY,
          'Authorization': `Bearer ${env.SUPABASE_SERVICE_KEY}`,
          'Content-Type': 'application/json',
          'Prefer': 'return=minimal',
        },
        body: JSON.stringify({
          referral_status: status,
          referral_reviewed_at: new Date().toISOString(),
        }),
      }
    );
    
    if (!sbRes.ok) {
      return json({ error: 'DB error: ' + await sbRes.text() }, 500);
    }
    
    return json({ ok: true, status });
    
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
