#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import uuid
import pandas as pd
import numpy as np
import datetime as dt
from settings import EARTH_RADIUS,server_type
from connections import connections,write_query
from database_entry import send_sms
from data_fetching import request_data_by_uuid,get_moderator_list
import mailer_fn as mailer
import urllib.parse as p
import requests


# In[ ]:



def get_haversine_distance(start_lat, start_lng, end_lat, end_lng, units='km'):
    try:
        # convert decimal degrees to radians
        lon1, lat1, lon2, lat2 = map(np.radians, [start_lng, start_lat, end_lng, end_lat])
    
        # haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = (np.sin(dlat / 2) ** 2 + np.cos(lat1) *
             np.cos(lat2) * np.sin(dlon / 2) ** 2)
        c = 2 * np.arcsin(np.sqrt(a))
    
        distance = EARTH_RADIUS * c
        if units=='m':
            return distance
        else:
            return distance / 1000.0
    except Exception as e:
        mailer.send_exception_mail()
        return None


# In[ ]:


def url_shortener_fn(input_url):
    url = 'http://tinyurl.com/api-create.php'
    params = {'url':input_url}
    request = requests.get(url=url,params=params)
    if(request.text=='Error'):
        return input_url
    else:
        return request.text


# In[ ]:


#Send message to all volunteers within 1km - to accept request
#Send message to all volunteers within 10kms - to help looking for volunteer
#Send message to all moderators about the both

def message_all_volunteers(uuid,radius,search_radius):
    v_list_q = """Select id as v_id,mob_number,name, latitude,longitude from volunteers where status=1"""
    v_list = pd.read_sql(v_list_q,connections('prod_db_read'))
    r_df = request_data_by_uuid(uuid)
    r_id = r_df.loc[0,'r_id']
    lat = r_df.loc[0,'latitude']
    lon = r_df.loc[0,'longitude']
    v_list['dist'] = get_haversine_distance(float(lat),float(lon),v_list['latitude'].astype(float).values,v_list['longitude'].astype(float).values)
    v_list = v_list.sort_values(by='dist',ascending=True)
    v_ids = pd.DataFrame()
    df = pd.DataFrame()
    df2 = pd.DataFrame()
    count=0
    if(server_type=='prod'):
        key_word = 'COVIDSOS'
        url_start = "https://covidsos.org/"
    else:
        key_word = 'TEST'
        url_start = "https://stg.covidsos.org/"
    for i in v_list.index:
        if(v_list.loc[i,'dist']<radius):
            orig_link = url_start+"accept/"+uuid
            link = url_shortener_fn(orig_link)
            sms_text = "["+key_word+"]. Dear "+v_list.loc[i,'name']+ ", HELP NEEDED in your area. Click "+link+" to help." 
            sms_to = int(v_list.loc[i,'mob_number'])
            df = df.append(v_list.loc[i,['v_id']])
            print(link)
            if((server_type=='prod')):
                send_sms(sms_text,sms_to,sms_type='transactional',send=True)
                print('SMS sent')
            else:
                print('Sending sms:',sms_text,' to ',str(sms_to))
        if((v_list.loc[i,'dist']>radius)&(v_list.loc[i,'dist']<search_radius)):
            count = count +1
            if(count>20):
                break
            orig_link = url_start+"accept/"+uuid
            link = url_shortener_fn(orig_link)
            print(link)
            sms_text = "["+key_word+"] HELP NEEDED in "+r_df.loc[0,'geoaddress'][0:40]+".. Click "+link+ " to help or refer someone."
            sms_to=int(v_list.loc[i,'mob_number'])
            df2 = df2.append(v_list.loc[i,['v_id']])
            if((server_type=='prod')):
                send_sms(sms_text,sms_to,sms_type='transactional',send=True)
                print('SMS sent')
            else:
                print('Sending sms:',sms_text,' to ',str(sms_to))
    df['r_id']=r_id
    df['status']='pending'
    print(v_list)
    print(df)
    print(df2)
    if((server_type=='prod')):
        engine = connections('prod_db_write')
        df.to_sql(name = 'nearby_volunteers', con = engine, schema='covidsos', if_exists='append', index = False,index_label=None)
    mod_sms_text = key_word+" New request verified. Sent to "+str(df.shape[0])+" nearby Volunteers and "+str(df2.shape[0])+" volunteers further away"
    mod_sms_text_2 = key_word+" Request #"+str(r_df.loc[0,'r_id'])+" New Request Name: "+r_df.loc[0,'name']+" Address: "+r_df.loc[0,'geoaddress'][0:50]+" Mob: "+str(r_df.loc[0,'mob_number'])+" Req:"+r_df.loc[0,'request']
    str_broadcast = "For request #"+str(r_df.loc[0,'r_id'])+ " "
    counter_broadcast = 0
    for i in v_list.index:
        counter_broadcast = counter_broadcast+1
        if((counter_broadcast>10) or (v_list.loc[i,'dist']>search_radius)):
            break
        str_broadcast = str_broadcast + v_list.loc[i,'name']+" m: wa.me/91"+str(v_list.loc[i,'mob_number'])+" "
    link = url_shortener_fn("https://wa.me/918618948661?text="+p.quote(str_broadcast))
    mod_sms_text_3 = "Broadcast to volunteers using "+link
    moderator_list = get_moderator_list()
    for i_number in moderator_list:
        if((server_type=='prod')):
            send_sms(mod_sms_text,sms_to=int(i_number),sms_type='transactional',send=True)
            send_sms(mod_sms_text_2,sms_to=int(i_number),sms_type='transactional',send=True)
            send_sms(mod_sms_text_3,sms_to=int(i_number),sms_type='transactional',send=True)
            print('SMS sent')
        else:
            print('Sending sms:',mod_sms_text,' to ',str(i_number))
            print('Sending sms:',mod_sms_text_2,' to ',str(i_number))
            print('Sending sms:',mod_sms_text_3,' to ',str(i_number))
    return None


# In[ ]:


def volunteer_accept(uuid,mob_number):
    v_list_q = """Select id as v_id,name as full_name from volunteers where mob_number='{mob_number}'""".format(mob_number=mob_number)
    v_list = pd.read_sql(v_list_q,connections('prod_db_read'))
    v_id = v_list.loc[0,'v_id']

    r_id_q = """Select id as r_id, mob_number as mob_number from requests where uuid='{uuid_str}'""".format(uuid_str=uuid)
    return None


# In[ ]:


def generate_uuid():
    uuid_key = str(uuid.uuid4()).replace('-', '')
    return uuid_key


# In[ ]:


def assignment_link(r_id):
    v_list_q = """Select id as v_id,mob_number,name, latitude,longitude from volunteers where status=1"""
    v_list = pd.read_sql(v_list_q,connections('prod_db_read'))
    v_list['dist'] = get_haversine_distance(lat,lon,)
    v_list = v_list.sort_values(by='dist',ascending=True)
    for i in v_list.index:
        if(v_list.loc[i,'dist']<'radius'):
            sms_text = 'Dear, '+v_list.loc[i,'name']+' someone in your area needs help. Click here to help '+link
            send_sms(sms_text,sms_to=v_list.loc[i,'mob_number'],sms_type='transactional',send=True)
    #incomplete
    return None
    


# In[ ]:





# In[ ]:




