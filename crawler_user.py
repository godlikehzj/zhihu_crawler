import requests
import codecs
import json
import time
from collections import deque
from bs4 import BeautifulSoup

from enum import Enum
class DebugLevel(Enum):
    verbose = 1
    warning = 2
    error = 3
    end = 4

class ZhihuCrawler(object):
    def __init__(self):
        self._base_url = r"https://www.zhihu.com"
        self._start_url = r"https://www.zhihu.com/topic/19551052/followers"
        self._debug_level = DebugLevel.verbose
        self._visited_user_url = set() #set 查找元素的时间复杂度是O(1)
        self._last_user_id = 1458573819
        self._offset = 40
        ZhihuCommon.session_init()
        self._config = self._load_config()

    def _load_config(self):
        struct = {"account": r"", "password": r"",
                    "Note": "account can be 'email' or 'phone number'"}
        try:
            with open(ZhihuCommon.config_json_file, "r", encoding = "utf-8") as fp:
                config = json.loads(fp.read())
                struct.update(config)
        except Exception as e:
            with open(ZhihuCommon.config_json_file, "w+", encoding = "utf-8") as fp:
                fp.write(json.dumps(struct, indent=4))
        finally:
            return struct

    def _save_user(self, user):
        with open(ZhihuCommon.user_json_file, "a", encoding = "utf-8") as fp:
            json_str = json.dumps(user, default = ZhihuUser.obj_to_dict, ensure_ascii = False, sort_keys = True)
            fp.write(json_str + "\n")

    def init_xsrf(self):
        """初始化，获取xsrf"""

        try:
            #下载线_的解释: it has the special meaning that "I don't need this variable, I'm only putting something
            # here because the API/syntax/whatever requires it"
            _, soup = ZhihuCommon.get(self._base_url)
            input_tag = soup.find("input", {"name": "_xsrf"})
            xsrf = input_tag["value"]
            ZhihuCommon.set_xsrf(xsrf)
        except Exception as e:
            self._debug_print(DebugLevel.error, "fail to init xsrf. " + str(e))


    def do_crawler(self):
        while (self._offset < 100000):
            post_dict = {
                'offset': self._offset,
                'start': self._last_user_id,
                '_xsrf': ZhihuCommon.get_xsrf(),
            }
            json_Str = ZhihuCommon.post(self._start_url, post_dict)
            user_json = json_Str.json()["msg"][1]
            soup = BeautifulSoup(user_json)
            users_id = soup.find_all("div", class_="zm-person-item")
            users_info = soup.find_all("a", class_="zm-list-avatar-medium")
            for user_info in users_info:
                author = ZhihuUser(self._base_url + user_info.attrs["href"])
                if author.is_valid():
                    self._save_user(author)
            user_num = len(users_id)
            self._offset += user_num
            self._last_user_id = int(users_id[user_num-1]["id"][3:])

    def login(self):
        """获取登录后的界面，需要先运行init_xsrf"""

        if not len(self._config["account"]):
            print("Please fill config.json with your account.")

        login_by = 'email' if '@' in self._config["account"] else 'phone_num'
        login_url = self._base_url + r"/login/" + login_by

        post_dict = {
            'remember_me': 'true',
            'password': self._config["password"],
            '_xsrf': ZhihuCommon.get_xsrf(),
        }
        post_dict.update({login_by: self._config["account"]})

        response_login = ZhihuCommon.post(login_url, post_dict)
        # response content: {"r":0, "msg": "\u767b\u9646\u6210\u529f" }
        return response_login.json()["r"] == 0
        #self._save_file('login_page.htm', reponse_login.text, reponse_login.encoding)

class ZhihuUser(object):
    _extra_info_key = ("education item", "education-extra item", "employment item", \
                      "location item", "position item");

    def __init__(self, user_url):
        self._debug_level = DebugLevel.verbose
        self._user_url = user_url
        self._valid = self._parse_user_page()
        if self._valid:
            self.parse_extra_info()

    def is_valid(self):
        return self._valid

    def get_url(self):
        return self._user_url

    def _debug_print(self, level, log_str):
        if level.value >= self._debug_level.value:
            print("[USER] " + log_str)

    def _save_file(self, path, str_content, encoding):
        with codecs.open(path, 'w', encoding)  as fp:
            fp.write(str_content)

    @staticmethod
    def obj_to_dict(obj):
        """把ZhihuUser转成dict数据，用于ZhihuCrawler。save_user中的json dump"""
        tmp_dict = {}
        tmp_dict["name"] = obj._name
        tmp_dict["url"] = obj._user_url
        tmp_dict["thank_cnt"] = obj._thank_cnt
        tmp_dict["agree_cnt"] = obj._agree_cnt
        tmp_dict["gender"] = obj._gender
        tmp_dict["img_url"] = obj._img_url
        for key_str in ZhihuUser._extra_info_key:
            if key_str in obj._extra_info:
                tmp_dict[key_str] = obj._extra_info[key_str]
            else:
                tmp_dict[key_str] = ""

        return tmp_dict

    def _parse_user_page(self):
        try:
            _, soup = ZhihuCommon.get(self._user_url)
            self.soup = soup
            #class_即是查找class，因为class是保留字，bs框架做了转化
            head_tag = soup.find("div", class_="zm-profile-header")
            name_tag = head_tag.find("span", class_="name")
            name = name_tag.contents[0]
            agree_tag = head_tag.find("span", class_="zm-profile-header-user-agree")
            agree_cnt = agree_tag.contents[1].contents[0]
            thank_tag = head_tag.find("span", class_="zm-profile-header-user-thanks")
            thank_cnt = thank_tag.contents[1].contents[0]
            img_url = soup.find("img", class_="Avatar Avatar--l")
            gender_tag = head_tag.find("span", class_="item gender")
            if (gender_tag == None):
                self._gender = "Unknown gender"
            else:
                #gender_tag.cont...nts[0]["class"]是一个list，list的每一个元素是字符串
                gender_str = gender_tag.contents[0]["class"][1]
                if gender_str.find("female") > 0:
                    self._gender = "Female"
                elif gender_str.find("male") > 0:
                    self._gender = "Male"
                else:
                    self._gender = "Unknown gender"
            self._name = name
            self._thank_cnt = int(thank_cnt)
            self._agree_cnt = int(agree_cnt)
            self._img_url = img_url.attrs["src"]
            is_ok = True
            self._debug_print(DebugLevel.verbose, "parse " + self._user_url + " ok. " + "name:" + self._name)
        except Exception as e:
            self._debug_print(DebugLevel.warning, "some exception raised by parsing " \
                             + self._user_url + "ErrInfo: " + str(e))
            is_ok = False
        finally:
            return is_ok

    def parse_extra_info(self):
        #<span class="position item" title="流程设计">
        self._extra_info = {}
        for key_str in self._extra_info_key:
            tag = self.soup.find("span", class_=key_str)
            if tag is not None:
                self._extra_info[key_str] = tag["title"]


    def __str__(self):
        #print类的实例打印的字符串
        out_str = "User " + self._name + " agree: " + str(self._agree_cnt) + ", " \
            "thank: " + str(self._thank_cnt) + " " + self._gender + " "

        for key_str in self._extra_info_key:
            if key_str in self._extra_info:
                out_str += " " + key_str + ": " + self._extra_info[key_str]

        return out_str

class ZhihuCommon(object):
    """ZhihuCrawler, ZhihuTopic, ZhihuUser三个类的共用代码, 包含一些服务于debug的函数, 共用的网页获取函数, 等。"""

    root_topic = 19776749 # 19776749 根话题  19776751 未归类  19778298 形而上
    unclassed_topic = 19776751
    my_header = {
        'Connection': 'Keep-Alive',
        'Accept': 'text/html, application/xhtml+xml, */*',
        'Accept-Language': 'zh-CN,zh;q=0.8',
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; WOW64; Trident/7.0; rv:11.0) like Gecko',
        'Accept-Encoding': 'gzip,deflate,sdch',
        'Host': 'www.zhihu.com',
        'DNT': '1'
    }

    """运行参数"""
    debug_fast_crawler = False #快速模式是否打开，当此模式打开时，不会遍历所有同类的信息，用于调试。
    traversal_level_max = 3 #深度优化遍历最大层数限制
    user_json_file = "user.json"
    answer_json_file = "answer.json"
    topic_json_file = "topic.json"
    config_json_file = "config.json"

    _last_get_page_fail = False #上一次调用get_page是失败的?
    _xsrf = None
    _session = None

    @staticmethod
    def set_xsrf(xsrf):
        ZhihuCommon._xsrf = xsrf

    @staticmethod
    def get_xsrf():
        return ZhihuCommon._xsrf

    @staticmethod
    def session_init():
        ZhihuCommon._session = requests.Session()

    @staticmethod
    def get_session():
        return ZhihuCommon._session

    @staticmethod
    def get(url):
        try_time = 0

        while try_time < 5:
            #上一次get页面失败，暂停10秒
            if ZhihuCommon._last_get_page_fail:
                time.sleep(10)

            try:
                try_time += 1
                response = ZhihuCommon.get_session().get(url, headers = ZhihuCommon.my_header, timeout = 30)
                #, cert = 'F:\Programs\Class-3-Public-Primary-Certification-Authority.pem')
                soup = BeautifulSoup(response.text, "html.parser")
                ZhihuCommon._last_get_page_fail = False
                return response.text, soup
            except Exception as e:
                print("fail to get " + url + " error info: " + str(e) + " try_time " + str(try_time))
                ZhihuCommon._last_get_page_fail = True
        else:
            raise #当前函数不知道应该怎么处理该错误，所以，最恰当的方式是继续往上抛，让顶层调用者去处理

    @staticmethod
    def post(url, post_dict):
        try_time = 0

        while try_time < 5:
            #上一次get页面失败，暂停10秒
            if ZhihuCommon._last_get_page_fail:
                time.sleep(10)

            try:
                try_time += 1
                response = ZhihuCommon.get_session().post(url, headers = ZhihuCommon.my_header, data = post_dict, timeout = 30)
                #, cert = 'F:\Programs\Class-3-Public-Primary-Certification-Authority.pem')
                ZhihuCommon._last_get_page_fail = False
                return response
            except Exception as e:
                print("fail to post " + url + " error info: " + str(e) + " try_time " + str(try_time))
                ZhihuCommon._last_get_page_fail = True
        else:
            raise #当前函数不知道应该怎么处理该错误，所以，最恰当的方式是继续往上抛，让顶层调用者去处理

    @staticmethod
    def get_and_save_page(url, path):
        try:
            response = ZhihuCommon.get_session().get(url, headers = ZhihuCommon.my_header,  verify = False)
            with codecs.open(path, 'w', response.encoding)  as fp:
                fp.write(response.text)
            return
        except Exception as e:
            print("fail to get " + url + " error info: " + str(e))
            return

def main():
    z = ZhihuCrawler()
    z.init_xsrf()
    login_sucess = z.login()
    if not login_sucess:
        print("fail to login.")
        return
    z.do_crawler()

    print("ok\n")

if __name__ == "__main__":
    main()


