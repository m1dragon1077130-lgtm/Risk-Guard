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
    const checkRes = await fetch(
      `${env.SUPABASE_URL}/rest/v1/users?github_id=eq.${sessionData.github_id}&select=referral_clicked,referral_status,github_username,github_name,github_avatar`,
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
    
    if (user.referral_status === 'pending') {
      return json({ error: 'درخواست شما در انتظار تایید است' }, 400);
    }
    
    if (user.referral_status === 'approved') {
      return json({ error: 'قبلاً تایید شدی' }, 400);
    }
    
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
          referral_status: 'pending',
          referral_requested_at: new Date().toISOString(),
        }),
      }
    );
    
    if (!sbRes.ok) {
      return json({ error: 'DB error: ' + await sbRes.text() }, 500);
    }
    
    // ارسال نوتیف به تلگرام
    if (env.TELEGRAM_BOT_TOKEN && env.TELEGRAM_CHAT_ID) {
      try {
        const message = `🔔 <b>درخواست جدید تایید رفرال</b>

👤 <b>کاربر:</b> ${user.github_username || 'نامعلوم'}
📧 <b>ایمیل:</b> ${user.github_name || 'نامعلوم'}
🆔 <b>GitHub ID:</b> ${sessionData.github_id}
⏰ <b>زمان:</b> ${new Date().toLocaleString('fa-IR')}

🔗 <a href="https://risk-guard.pages.dev/admin.html">ورود به پنل ادمین</a>`;
        
        const tgRes = await fetch(
          `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              chat_id: env.TELEGRAM_CHAT_ID,
              text: message,
              parse_mode: 'HTML',
              disable_web_page_preview: true,
            }),
          }
        );
        
        if (!tgRes.ok) {
          console.error('Telegram error:', await tgRes.text());
        }
      } catch (tgErr) {
        console.error('Telegram exception:', tgErr);
      }
    }
    
    return json({ ok: true });
    
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
