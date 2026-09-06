# accounts/adapters.py
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        
        # Check if the user was just created and retrieve role from session
        role = request.session.get('user_role', 'CUSTOMER')
        user.role = role
        user.save()
        
        # Clean up session key
        if 'user_role' in request.session:
            del request.session['user_role']
            
        return user