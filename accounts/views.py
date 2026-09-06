from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404

from .serializers import EmailRegisterSerializer
from .models import User
from django.contrib.auth.decorators import login_required

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator

class EmailRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EmailRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "message": "Registration successful. Please verify your email.",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "isEmailVerified": user.is_email_verified
                },
                "tokens": serializer.data["tokens"]
            },
            status=status.HTTP_201_CREATED
        )

class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        user = get_object_or_404(User, email_verification_token=token)

        if user.email_verification_expiry < timezone.now():
            return Response(
                {"error": "Verification token has expired"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.is_email_verified = True
        user.email_verification_token = None
        user.email_verification_expiry = None
        user.save()

        return Response(
            {"message": "Email verified successfully"},
            status=status.HTTP_200_OK
        )
class ResendVerificationEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")

        user = get_object_or_404(User, email=email)

        if user.is_email_verified:
            return Response(
                {"message": "Email already verified"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.generate_email_verification()
        send_verification_email(user)

        return Response(
            {"message": "Verification email resent"},
            status=status.HTTP_200_OK
        )



from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login

def login_view(request):
    error = None

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, email=username, password=password)
        if user is not None:
            login(request, user)
            # Redirect based on user type
            if user.is_superuser:
                return redirect("addProduct")  # Django admin panel
            else:
                return redirect("home:home")  # regular user home page
        else:
            error = "Invalid username or password"

    return render(request, "Login.html", {"error": error})
@require_POST
def login_api(request):
    username = request.POST.get("username")
    password = request.POST.get("password")

    user = authenticate(request, email=username, password=password)

    if user is not None:
        login(request, user)

        return JsonResponse({
            "success": True,
            "redirect": "/Adminpanel/Products/products/add/" if user.is_superuser else "/"
        })

    return JsonResponse({
        "success": False,
        "message": "Invalid username or password"
    }, status=400)
from django.contrib import messages
from django.contrib.auth.hashers import make_password

def register_view(request):
    error = None
    # Pre-fill dictionary
    initial_data = {
        "full_name": "",
        "email": "",
        "mobile": ""
    }

    if request.method == "POST":
        full_name = request.POST.get("full_name")
        email = request.POST.get("email")
        mobile = request.POST.get("mobile")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        # Preserve entered values
        initial_data = {
            "full_name": full_name,
            "email": email,
            "mobile": mobile
        }

        # Validation
        if not full_name or not email or not password1:
            error = "Full name, email, and password are required."
        elif password1 != password2:
            error = "Passwords do not match."
        elif User.objects.filter(email=email).exists():
            error = "Email is already registered."
        elif mobile and User.objects.filter(mobile=mobile).exists():
            error = "Mobile number is already registered."
        else:
            # Create user
            user = User(
                full_name=full_name,
                email=email,
                mobile=mobile,
                password=make_password(password1)
            )
            user.save()
            messages.success(request, "Account created successfully! Please login.")
            return redirect("login")

    return render(request, "register.html", {"error": error, "data": initial_data})
from django.http import JsonResponse
from django.contrib.auth.hashers import make_password
from django.views.decorators.http import require_POST

from django.core.validators import validate_email
from django.core.exceptions import ValidationError

@require_POST
def register_api(request):

    full_name = request.POST.get("full_name", "").strip()
    email = request.POST.get("email", "").strip().lower()
    mobile = request.POST.get("mobile", "").strip()
    password1 = request.POST.get("password1", "")
    password2 = request.POST.get("password2", "")


    # -----------------------------------------
    # FULL NAME
    # -----------------------------------------

    if not full_name:

        return JsonResponse({
            "success": False,
            "field": "full_name",
            "message": "Full name is required."
        })


    if len(full_name) < 2:

        return JsonResponse({
            "success": False,
            "field": "full_name",
            "message": "Full name must contain at least 2 characters."
        })


    # -----------------------------------------
    # EMAIL
    # -----------------------------------------

    if not email:

        return JsonResponse({
            "success": False,
            "field": "email",
            "message": "Email is required."
        })


    try:
        validate_email(email)

    except ValidationError:

        return JsonResponse({
            "success": False,
            "field": "email",
            "message": "Please enter a valid email address."
        })


    if User.objects.filter(email__iexact=email).exists():

        return JsonResponse({
            "success": False,
            "field": "email",
            "message": "Email is already registered."
        })


    # -----------------------------------------
    # MOBILE
    # -----------------------------------------

    if mobile:

        if not mobile.isdigit():

            return JsonResponse({
                "success": False,
                "field": "mobile",
                "message": "Mobile number must contain digits only."
            })


        if len(mobile) != 11:

            return JsonResponse({
                "success": False,
                "field": "mobile",
                "message": "Mobile number must be exactly 11 digits."
            })


        if not mobile.startswith("03"):

            return JsonResponse({
                "success": False,
                "field": "mobile",
                "message": "Mobile number must start with 03. Example: 03001234567."
            })


        if User.objects.filter(mobile=mobile).exists():

            return JsonResponse({
                "success": False,
                "field": "mobile",
                "message": "Mobile number is already registered."
            })


    # -----------------------------------------
    # PASSWORD
    # -----------------------------------------

    if not password1:

        return JsonResponse({
            "success": False,
            "field": "password1",
            "message": "Password is required."
        })


    if len(password1) < 8:

        return JsonResponse({
            "success": False,
            "field": "password1",
            "message": "Password must contain at least 8 characters."
        })


    # -----------------------------------------
    # CONFIRM PASSWORD
    # -----------------------------------------

    if not password2:

        return JsonResponse({
            "success": False,
            "field": "password2",
            "message": "Please confirm your password."
        })


    if password1 != password2:

        return JsonResponse({
            "success": False,
            "field": "password2",
            "message": "Passwords do not match."
        })


    # -----------------------------------------
    # CREATE USER
    # -----------------------------------------

    user=User.objects.create(
        full_name=full_name,
        email=email,
        mobile=mobile,
        password=make_password(password1)
    )
    login( request, user, backend="django.contrib.auth.backends.ModelBackend" )

    # -----------------------------------------
    # SUCCESS
    # -----------------------------------------

    return JsonResponse({
        "success": True,
        "message": "Account created successfully.",
        "redirect_url": "/login/"
    })

from django.contrib.auth import logout

def logout_view(request):
    logout(request)
    return redirect("login")  # redirect to login page



from rest_framework import viewsets,permissions
from rest_framework.decorators import action
from .serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):

    queryset = User.objects.prefetch_related("roles")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]


    def list(self, request):
        users = self.get_queryset().order_by("-date_joined")
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)


    @action(detail=True, methods=["post"])
    def toggle_status(self, request, pk=None):
        """
        Toggle the user's active status (block/unblock).
        """
        user = self.get_object()
        user.is_active = not user.is_active
        user.save()
        status_str = "unblocked" if user.is_active else "blocked"
        return Response({
            "message": f"User has been {status_str}.",
            "is_active": user.is_active
        })
    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):

        user = self.get_object()
        user.is_active = False
        user.save()

        return Response({"message": "User blocked"})


    @action(detail=True, methods=["post"])
    def unblock(self, request, pk=None):

        user = self.get_object()
        user.is_active = True
        user.save()

        return Response({"message": "User unblocked"})




@login_required
def users_page(request):
    
    return render(request, "users.html")



from .models import User, Address
from Web.models import UserWallet, UserWalletTransaction

@login_required
def profile_view(request):
    user = request.user
    addresses = user.addresses.all()
    
    # Wallet info (assuming you have Wallet and WalletTransaction models)
    wallet = getattr(user, 'UserWallet', None)  # OneToOneField relation
    transactions = UserWalletTransaction.objects.filter(wallet=UserWallet).order_by('-date') if wallet else []

    context = {
        'user': user,
        'addresses': addresses,
        'wallet': wallet,
        'transactions': transactions,
    }
    return render(request, 'Profile.html', context)

@login_required
@require_POST
def update_profile_ajax(request):
    """
    Update user's profile via AJAX
    """
    user = request.user

    # Get data from POST
    full_name = request.POST.get('full_name')
    email = request.POST.get('email')
    mobile = request.POST.get('mobile')
    dob = request.POST.get('dob')
    gender = request.POST.get('gender')

    # Basic validation (optional: you can enhance)
    if not full_name or not email or not mobile:
        return JsonResponse({"status": "error", "message": "Full name, email, and mobile are required."})

    # Update user
    user.full_name = full_name
    user.email = email
    user.mobile = mobile
    user.dob = dob if dob else None
    user.gender = gender
    user.save()

    return JsonResponse({"status": "success", "message": "Profile updated successfully."})


def manual_account_login_required(request):
    return render(
        request,
        "account/manual_account_login_required.html"
    )