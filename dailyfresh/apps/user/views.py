from django.shortcuts import render,redirect
from django.core.urlresolvers import reverse
# from django.core.mail import send_mail
from django.contrib.auth import authenticate,login,logout
from django.views.generic import View
from django.http import HttpResponse
from django.conf import settings


from user.models import User,Address
from goods.models import GoodsSKU
from celery_tasks.tasks import send_register_active_email
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from utils.mixin import LoginRequirdeMixin
from django_redis import get_redis_connection
import re
import time

# Create your views here.

def register(request):
    '''显示注册页面'''
    if request.mothod == 'GET':
        return render(request,'register.html')
    else:
        '''进行注册处理'''
        # 接收数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 进行数据校验
        if not all([username, password, email]):
            # 数据不完整
            return render(request, 'register.html', {'errmsg': '数据不完整'})

        # 校验邮箱
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱格式不正确'})

        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请同意协议'})

        # 校验用户名是否重复
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # 用户名不存在
            user = None
        if user:
            return render(request, 'register.html', {'errmsg': '用户名已存在'})
        # 进行业务处理：进行用户注册
        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()

        # 返回应答，跳转到首页
        return redirect(reverse('goods:index'))

def register_handle(request):
    '''进行注册处理'''
    # 接收数据
    username = request.POST.get('user_name')
    password = request.POST.get('pwd')
    email = request.POST.get('email')
    allow = request.POST.get('allow')

    # 进行数据校验
    if not all([username, password, email]):
        # 数据不完整
        return render(request, 'register.html', {'errmsg':'数据不完整'})

    # 校验邮箱
    if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
        return render(request, 'register.html', {'errmsg':'邮箱格式不正确'})

    if allow != 'on':
        return render(request, 'register.html', {'errmsg':'请同意协议'})

    # 校验用户名是否重复
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        # 用户名不存在
        user = None

    if user:
        # 用户名已存在
        return render(request, 'register.html', {'errmsg':'用户名已存在'})

    # 进行业务处理: 进行用户注册
    user = User.objects.create_user(username, email, password)
    user.is_active = 0
    user.save()




    # 返回应答, 跳转到首页
    return redirect(reverse('goods:index'))

# 类视图，根据请求方式返回不同的处理
# /user/trgister
class RegisterView(View):
    '''注册'''
    def get(self,request):
        '''显示注册处理'''
        return render(request,'register.html')

    def post(self,request):
        '''进行注册处理'''
        # 接收数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        cpassword = request.POST.get('cpwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 进行数据校验
        if not all([username, password, email]):
            # 数据不完整
            return render(request, 'register.html', {'errmsg': '数据不完整'})

        # 校验确认密码
        if password != cpassword:
            return render(request,'register.html',{'errmsg':'两次密码不一样'})

        # 校验邮箱
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱格式不正确'})

        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请同意协议'})

        # 校验用户名是否重复
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # 用户名不存在
            user = None
        if user:
            return render(request, 'register.html', {'errmsg': '用户名已存在'})
        # 进行业务处理：进行用户注册
        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()

        # 发送激活邮件，包含激活链接：http：//127.0.0.1:8000/user/active/3
        # 激活链接中需要用户的身份信息，并且把身份信息进行加密
        # 加密用户的身份信息，生成激活token
        serializer = Serializer(settings.SECRET_KEY,3600)
        info = {'confirm':user.id}
        token = serializer.dumps(info).decode()

        # 发邮件：celery异步发送
        send_register_active_email.delay(email,username,token)
        # 返回应答，跳转到首页
        return redirect(reverse('goods:index'))

# 激活用户
class ActiveView(View):
    '''用户激活'''
    def get(self,request,token):
        '''进行用户激活'''
        # 进行解密，获取要激活用户信息
        serializer = Serializer(settings.SECRET_KEY, 3600)

        try:
            info = serializer.loads(token)
            # 获取待激活用户的id
            user_id = info['confirm']
            # 根据id获取用户信息
            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save()

            # 跳转到登陆页面
            return redirect(reverse('user:login'))

        except SignatureExpired as e:
            # 激活链接已过期
            return HttpResponse('激活链接已过期')

# /user/login
class LoginView(View):
    '''显示登陆页面'''
    def get(self,request):
        # 判断是否记住了用户名
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')
            checked = 'checked'
        else:
            username = ''
            checked = ''
            # 使用模板
        return render(request,'login.html',{'username':username,'checked':checked})

    def post(self,request):
        '''登陆校验'''
        # 接收数据
        username = request.POST.get('username')
        password = request.POST.get('pwd')
        # 校验数据
        if not all([username,password]):
            return render(request,'login.html',{'errmsg':'数据不完整'})
        # 进行业务处理：登陆校验(数据库)
        user = authenticate(username=username,password=password)
        if user is not None:
            if user.is_active:
                # 用户已激活
                # 记录用户的登陆状态,判断是否登录
                login(request,user)

                # 跳转到首页
                # 获取登录后所要跳转到的地址,如果不是从其它页面跳转过来的，它的值为None，然后默认跳到首页,比如用户中心转过来的
                next_url = request.GET.get('next', reverse('goods:index')) # None

                # 跳转到next_url

                response = redirect(next_url) # HttpResponseRedirect

                # 判断是否需要记住用户名
                remember = request.POST.get('remember')

                if remember == 'on':
                    response.set_cookie('username',username,max_age=7*24*3600)
                else:
                    response.delete_cookie('username')
                # 返回response
                return response

            else:
                # 用户未激活
                return render(request,'login.html',{'errmsg':'用户未激活'})
        else:
            # 用户名或密码错误
            return render(request,'login.html',{'errmsg':'用户名或密码错误'})

# /user/logout
class LogoutView(View):
    '''退出登录'''
    def get(self,request):
        # 清除用户的session信息
        logout(request)
        # 跳转到首页
        return redirect(reverse('goods:index'))

# /user
class UserInfoView(LoginRequirdeMixin,View):
    '''用户中心-信息页'''
    def get(self,request):
        '''显示'''
        # page = 'user'
        # request.user.is_authenticated()
        # request.user 如果用户未登录-> AnonymousUser类的一个实例 is_authenticated()方法返回False
        # 如果用户登录了 -> User类的一个实例 返回True

        # 获取用户的个人信息
        user = request.user
        address = Address.objects.get_default_address(user)
        # 获取用户的历史浏览信息
        # from redis import StrictRedis
        # StrictRedis(host='192.168.1.5:6379', port='6379', db=9)

        con = get_redis_connection('default')

        history_key = 'history_%d'%user.id

        # 获取用户最新浏览的5个商品的id
        sku_ids = con.lrange(history_key,0,4)

        # 从数据库中查询用户浏览的具体信息
        # goods_li = GoodsSKU.objects.filter(id__in=sku_ids)
        #
        # goods_res = []
        # for a_id in sku_ids:
        #     for goods in goods_li:
        #         if a_id == goods.id:
        #             goods_res.append(goods)

        # 遍历获取用户浏览的商品信息
        goods_li = []
        for id in sku_ids:
            goods = GoodsSKU.objects.get(id=id)
            goods_li.append(goods)

        # 组织上下文
        context = {
            'page': 'user',
            'address': address,
            'goods_li': goods_li,
        }


        # 除了你给模板文件传递的模板变量之外，django框架会把request.suer也传给模板文件
        return render(request,'user_center_info.html',context)

# /user/order
class UserOrderView(LoginRequirdeMixin,View):
    '''用户中心-订单页'''
    def get(self,request):
        '''显示'''
        # 获取用户的订单信息

        # page = 'order'
        return render(request,'user_center_order.html',{'page':'order'})

# /user/address
class AddressView(LoginRequirdeMixin,View):
    '''用户中心-地址页'''
    def get(self,request):
        '''显示'''

        # 获取登录用户对应User对象
        user = request.user
        # 获取用户的默认收货地址
        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     # 不存在默认收货地址
        #     address = None
        address = Address.objects.get_default_address(user)

        # page = 'address'
        return render(request,'user_center_site.html',{'page':'address','address':address})

    def post(self,request):
        '''地址的添加'''
        # 接收数据
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')

        # 校验数据
        if not all([receiver,addr,phone]):
            return render(request,'user_center_site.html',{'errmsg':'数据不完整'})

        # 校验手机号
        if not re.match(r'^1[3|4|5|6|7|8][0-9]{9}$',phone):
            return render(request,'user_center_site.html',{'errmsg':'手机号码不正确'})
        # 业务处理：地址添加
        # 如果用户已存在默认收货地址，添加的地址不作为默认收货地址，否则作为默认收货地址
        # 获取登录用户对应User对象
        user = request.user

        address = Address.objects.get_default_address(user)

        if address:
            is_default = False
        else:
            is_default = True

        # 添加地址
        Address.objects.create(user = user,receiver = receiver, addr = addr,zip_code = zip_code,phone = phone,is_default=is_default)
        # 返回应答,刷新地址页面
        return redirect(reverse('user:address'))
